"""Paper-trade executor — open / close / MTM for one bot.

NO BROKER CALLS. Fills use mid prices passed in by the caller; this module
never imports anything from Tradier. Keeps the paper-only invariant explicit.

SLIPPAGE MODEL
--------------
A raw mid-fill is a fiction: a real multi-leg order crosses part of the
bid/ask spread on EVERY leg, on entry AND exit. `slippage_per_leg` is the
half-spread (in $/share) we assume we give up per leg per side. It bites in
two places, so a round trip pays it 2 x n_legs times:

  * entry  (`open_position`) — a credit you SELL fills LOWER, a debit you BUY
    fills HIGHER, each by n_legs * slip.
  * exit   (`compute_mtm`)   — buying the structure back costs MORE by
    n_legs * slip; the buyback close (`close_position` at close_reason
    != SETTLE) inherits that worse mark automatically.

Cash SETTLE closes book intrinsic value with NO spread, so slippage is only
ever applied to quote-based marks, never to settlement.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .db import bot_table, load_config
from .strategies import CREDIT_STRATEGIES

# Debit structures whose liquidation value is bounded below by ZERO (a long
# fly is worth 0..wing at any price; the pin+drift combo is the fly plus two
# long calendars, each also >= 0). A computed negative unwind value for these
# can only be quote noise — clamped in compute_mtm.
NET_LONG_DEBIT_STRATEGIES = frozenset({"long_butterfly", "pin_drift_combo"})

# Default half-spread crossed per leg per side, $/share. 0.02 is a realistic
# figure for the SPY 0/1DTE options these bots trade (near-ATM shorts sit a
# penny or two wide; the cheap OTM wings are proportionally far wider). The
# scanner reads this via `configured_slippage_per_leg` and passes it down;
# the executor functions themselves default to 0.0 so unit tests that call
# them directly keep their exact-arithmetic expectations. Override live with
# env SPREADWORKS_SLIP_PER_LEG or a `slippage_per_leg` bot-config column.
DEFAULT_SLIPPAGE_PER_LEG = 0.02

logger = logging.getLogger("spreadworks.bots.executor")


def configured_slippage_per_leg(cfg: dict[str, Any] | None = None) -> float:
    """Resolve the per-leg slippage: bot config > env > DEFAULT.

    `cfg` is a loaded bot-config row (may lack the key on un-migrated tables).
    Returns 0.0 only if explicitly configured to 0.
    """
    if cfg is not None and cfg.get("slippage_per_leg") is not None:
        try:
            return max(0.0, float(cfg["slippage_per_leg"]))
        except (TypeError, ValueError):
            pass
    env = os.environ.get("SPREADWORKS_SLIP_PER_LEG")
    if env is not None:
        try:
            return max(0.0, float(env))
        except (TypeError, ValueError):
            pass
    return DEFAULT_SLIPPAGE_PER_LEG


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
    notes: str | None = None,
    *,
    slippage_per_leg: float = 0.0,
    mid_fill: bool = True,
) -> str:
    """Insert one OPEN row into {bot}_positions, return position_id.

    `slippage_per_leg` crosses the spread on the entry fill (see module
    docstring). `mid_fill=False` marks a fill that ALREADY crossed the book
    (e.g. UPDRAFT's patient limit that only triggers when the real ask
    touches) so it is not double-charged.
    """
    pid = _new_position_id(bot, now)
    t = bot_table(bot, "positions")
    # All signals expose .legs(), .pt_target_pnl, .sl_target_pnl, .max_profit,
    # .max_loss, .contracts, .ticker plus EITHER .credit (IBF) OR .debit (DC/DD).
    is_credit = hasattr(signal, "credit")
    entry_price = signal.credit if is_credit else signal.debit
    legs_json = json.dumps(signal.legs())
    if mid_fill and slippage_per_leg > 0:
        n_legs = len(signal.legs())
        adj = n_legs * slippage_per_leg
        # Cross the spread: a credit sold fills lower, a debit bought higher.
        mid_entry = entry_price
        entry_price = round(entry_price - adj, 4) if is_credit else round(entry_price + adj, 4)
        slip_note = f"slip {slippage_per_leg:.3f}/leg x{n_legs} (mid={mid_entry:.4f})"
        notes = f"{notes}; {slip_note}" if notes else slip_note
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO {t} ("
            "position_id, ticker, strategy, legs, entry_price, contracts, entry_time, "
            "status, mtm_value, mtm_pnl, mtm_updated_at, pt_target_pnl, sl_target_pnl, "
            "max_profit, max_loss, account_label, notes"
            ") VALUES ("
            ":pid, :tk, :st, :legs, :ep, :ct, :et, 'OPEN', :mv, 0, :et, "
            ":pt, :sl, :mp, :ml, 'paper', :notes"
            ")"
        ), {
            "pid": pid, "tk": signal.ticker, "st": strategy, "legs": legs_json,
            "ep": entry_price, "ct": signal.contracts, "et": now,
            "mv": entry_price,
            "pt": signal.pt_target_pnl, "sl": signal.sl_target_pnl,
            "mp": signal.max_profit * signal.contracts,
            "ml": signal.max_loss * signal.contracts,
            "notes": notes,
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


def count_positions_opened_on(engine: Engine, bot: str, now: datetime) -> int:
    """Count positions (any status) whose entry_time falls on `now`'s date.

    Used by the stacking gate to cap MEADOW at one new entry per entry-day:
    closed rows are retained in {bot}_positions, so a position opened and
    closed earlier the same day still counts. Mirrors the dialect-portable
    `DATE(col) = DATE(:n)` comparison used in the equity-snapshot query.
    """
    t = bot_table(bot, "positions")
    with engine.begin() as conn:
        row = conn.execute(text(
            f"SELECT COUNT(*) AS c FROM {t} WHERE DATE(entry_time) = DATE(:n)"
        ), {"n": now}).mappings().first()
    return int(row["c"] or 0)


def compute_mtm(
    *,
    strategy: str,
    legs: list[dict[str, Any]],
    entry_price: float,
    contracts: int,
    leg_mids: Iterable[float] | None = None,
    cost_to_close_override: float | None = None,
    slippage_per_leg: float = 0.0,
) -> tuple[float, float]:
    """Return (mtm_value, mtm_pnl).

    `leg_mids` must align with `legs` (same order). Each mid is the current
    market mid for that leg.

    `slippage_per_leg` models the cost of buying the structure back: the
    cost-to-close is worsened by n_legs * slip (see module docstring). This
    is the EXIT half of the round-trip cost (entry half lives in
    open_position); a non-SETTLE close consumes this same worsened mark.

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

    # Slippage on the EXIT fill: crossing the spread on every leg makes a
    # buyback cost MORE (credit) / an unwind fetch LESS (debit). n_legs is
    # taken from the structure; the override path (tests) still gets it.
    exit_slip = len(legs) * slippage_per_leg if slippage_per_leg > 0 else 0.0

    if strategy in CREDIT_STRATEGIES:
        # Credit strategies (IBF, IC, credit double diagonal): mtm_value
        # already reads as "cost to buy back the structure"; pnl is (credit
        # received - cost to close) × contracts × $100/share.
        mtm_value += exit_slip
        mtm_pnl = (entry_price - mtm_value) * contracts * 100.0
    else:
        # For debit strats, mtm_value above is signed as "cost to buy in",
        # but for DC/DD we want "current credit to unwind" — flip sign:
        mtm_value = -mtm_value
        mtm_value -= exit_slip
        if strategy in NET_LONG_DEBIT_STRATEGIES and mtm_value < 0.0:
            # These structures can't be worth less than zero; a negative
            # unwind value is stale/one-sided leg quotes. Floor at 0 so mark
            # noise can never book a loss deeper than the debit (2026-07-06..08:
            # negative combo marks closed SPLASH/SURGE trades at impossible
            # prices, e.g. -$175.50 realized on a $165 max-loss position).
            mtm_value = 0.0
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
