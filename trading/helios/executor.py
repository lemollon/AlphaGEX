"""
HELIOS - Paper Trade Executor
=============================

Open and close paper positions for the HELIOS 1DTE directional bot.

This module owns the debit/PnL math but no broker plumbing — it's purely
synchronous, paper-only. Live execution will be a separate module so the
math here can be exercised under unit tests without any external deps.

Pricing convention (debit vertical spread):
    debit         = long_mid - short_mid          # per share
    cost_per_ctr  = debit * 100                   # per contract
    contracts     = floor(risk_per_trade / cost_per_ctr)
    realized_pnl  = (mark_to_close - debit) * 100 * contracts
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Optional

from .db import HeliosDatabase
from .models import HeliosConfig, SpreadType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenedPosition:
    position_id: int
    debit: float
    contracts: int


def open_paper(
    *,
    db: HeliosDatabase,
    spread_type: SpreadType,
    long_symbol: str,
    short_symbol: str,
    long_strike: float,
    short_strike: float,
    long_mid: float,
    short_mid: float,
    expiration_date: dt.date,
    config: HeliosConfig,
) -> Optional[OpenedPosition]:
    """
    Compute debit + contract size and insert a new OPEN position.

    Returns None (without inserting) if the debit is invalid or the
    risk budget cannot fund a single contract.
    """
    debit = float(long_mid) - float(short_mid)
    if debit <= 0 or debit >= config.spread_width:
        logger.info("DEBIT_INVALID debit=%.4f", debit)
        return None

    cost_per_contract = debit * 100.0
    contracts = int(config.risk_per_trade // cost_per_contract)
    if contracts < 1:
        logger.info("SIZE_BELOW_1_CONTRACT debit=%.4f", debit)
        return None

    pid = db.insert_position(
        spread_type=spread_type.value,
        long_symbol=long_symbol,
        short_symbol=short_symbol,
        long_strike=long_strike,
        short_strike=short_strike,
        expiration_date=expiration_date,
        contracts=contracts,
        debit=debit,
    )
    return OpenedPosition(position_id=pid, debit=debit, contracts=contracts)


def close_paper(
    *,
    db: HeliosDatabase,
    position_id: int,
    mark_to_close: float,
    exit_reason: str,
) -> float:
    """
    Close an open position at the given mark and persist realized P&L.

    Returns the realized_pnl (in dollars).
    """
    pos = db.get_position(position_id)
    if pos is None:
        raise ValueError(f"HELIOS close_paper: position {position_id} not found")

    debit = float(pos["debit"])
    contracts = int(pos["contracts"])
    realized_pnl = (float(mark_to_close) - debit) * 100.0 * contracts

    db.close_position(
        position_id,
        close_price=float(mark_to_close),
        realized_pnl=realized_pnl,
        exit_reason=exit_reason,
    )
    db.bump_realized_pnl(realized_pnl)
    return realized_pnl
