"""GOLIATH gate orchestrator -- runs G01..G10 in order, persists failures.

Master spec section 2: all 10 gates must pass. The orchestrator stops
on the first non-PASS result, logs a row to ``goliath_gate_failures``
(migration 028), and returns the chain so the caller can decide what
to do (typically: skip the trade and move on).

Public API:
    orchestrate_entry(inputs: GateInputs) -> EntryDecision

Persistence is best-effort -- a database failure does not change the
gate decision. The chain is always returned in full so callers can
log it elsewhere if the DB write fails.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Sequence

from trading.goliath.models import GoliathConfig
from trading.goliath.strike_mapping.engine import TradeStructure
from trading.goliath.strike_mapping.wall_finder import GammaStrike

from . import (
    g01_spy_gex,
    g02_underlying_gex,
    g03_wall_present,
    g04_earnings_window,
    g05_iv_rank,
    g06_oi_per_leg,
    g07_bid_ask_per_leg,
    g08_net_cost_ratio,
    g09_ma_trend,
    g10_platform_position_cap,
)
from .base import GateOutcome, GateResult

logger = logging.getLogger(__name__)


@dataclass
class GateInputs:
    """All data needed to evaluate gates G01-G10."""

    letf_ticker: str
    underlying_ticker: str
    spy_net_gex: float
    underlying_net_gex: float
    underlying_strikes: Sequence[GammaStrike]
    underlying_spot: float
    next_earnings_date: Optional[date]
    iv_rank: Optional[float]
    underlying_50d_ma: Optional[float]
    open_position_count: int
    config: GoliathConfig
    attempted_structure: Optional[TradeStructure] = None
    today: Optional[date] = None


@dataclass
class EntryDecision:
    """Result of running the gate chain.

    structure: the TradeStructure to trade if all gates passed; None otherwise.
    chain: ordered list of GateResults (PASSes followed by the first non-PASS,
        or all 10 PASSes when the structure is approved).
    """

    structure: Optional[TradeStructure]
    chain: list[GateResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.structure is not None and all(r.passed for r in self.chain)

    @property
    def first_failure(self) -> Optional[GateResult]:
        for r in self.chain:
            if not r.passed:
                return r
        return None


def _structure_unavailable(gate_id: str) -> GateResult:
    """Synthesize a FAIL when a post-structure gate has no structure to evaluate."""
    return GateResult(
        gate=gate_id,
        outcome=GateOutcome.FAIL,
        reason="attempted_structure unavailable -- strike mapping did not produce one",
        context={"structure_present": False},
    )


def _eval_chain(inputs: GateInputs) -> list[GateResult]:
    """Run gates G01-G10 in order, stopping at the first non-PASS."""
    chain: list[GateResult] = []

    def _step(result: GateResult) -> bool:
        chain.append(result)
        return result.passed

    # G01-G05: pre-structure regime / data gates
    if not _step(g01_spy_gex.evaluate(inputs.spy_net_gex)):
        return chain
    if not _step(g02_underlying_gex.evaluate(inputs.underlying_ticker, inputs.underlying_net_gex)):
        return chain
    if not _step(g03_wall_present.evaluate(inputs.underlying_strikes, inputs.underlying_spot, inputs.config)):
        return chain
    if not _step(g04_earnings_window.evaluate(inputs.underlying_ticker, inputs.next_earnings_date, today=inputs.today)):
        return chain
    if not _step(g05_iv_rank.evaluate(inputs.letf_ticker, inputs.iv_rank)):
        return chain

    # G06-G08: structure-dependent gates
    s = inputs.attempted_structure
    if s is None:
        chain.append(_structure_unavailable("G06"))
        return chain
    if not _step(g06_oi_per_leg.evaluate(s.short_put, s.long_put, s.long_call)):
        return chain
    if not _step(g07_bid_ask_per_leg.evaluate(s.short_put, s.long_put, s.long_call)):
        return chain
    if not _step(g08_net_cost_ratio.evaluate(s.short_put, s.long_put, s.long_call)):
        return chain

    # G09-G10: trend + platform cap
    if not _step(g09_ma_trend.evaluate(inputs.underlying_ticker, inputs.underlying_spot, inputs.underlying_50d_ma)):
        return chain
    if not _step(g10_platform_position_cap.evaluate(inputs.open_position_count)):
        return chain

    return chain


def orchestrate_entry(inputs: GateInputs) -> EntryDecision:
    """Run the gate chain and return EntryDecision (with persisted failure)."""
    chain = _eval_chain(inputs)
    failed = next((r for r in chain if not r.passed), None)
    structure = inputs.attempted_structure if failed is None else None

    if failed is not None:
        try:
            _persist_failure(inputs, chain, failed)
        except Exception as exc:  # noqa: BLE001
            logger.warning("goliath_gate_failures persist failed: %r", exc)

    return EntryDecision(structure=structure, chain=chain)


def _structure_to_jsonable(s: Optional[TradeStructure]) -> Optional[dict]:
    if s is None:
        return None
    return {
        "short_put_strike": s.short_put.strike,
        "long_put_strike": s.long_put.strike,
        "long_call_strike": s.long_call.strike,
        "put_spread_credit": s.put_spread_credit,
        "long_call_cost": s.long_call_cost,
        "net_cost": s.net_cost,
    }


def _persist_failure(inputs: GateInputs, chain: list[GateResult], failed: GateResult) -> None:
    """Best-effort write to goliath_gate_failures. Swallows DB errors."""
    try:
        from database_adapter import get_connection, is_database_available  # type: ignore
    except ImportError:
        logger.info("database_adapter not importable; skipping persist")
        return
    if not is_database_available():
        logger.info("DATABASE_URL unset; skipping persist")
        return

    passed_before = [r.gate for r in chain if r.passed]
    payload = (
        inputs.letf_ticker,
        inputs.underlying_ticker,
        failed.gate,
        failed.outcome.value,
        json.dumps(passed_before),
        json.dumps(_structure_to_jsonable(inputs.attempted_structure)),
        failed.reason,
        json.dumps(failed.context, default=str),
    )

    conn = get_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO goliath_gate_failures (
                    letf_ticker, underlying_ticker, failed_gate, failure_outcome,
                    gates_passed_before_failure, attempted_structure,
                    failure_reason, context
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                payload,
            )
            conn.commit()
        finally:
            cur.close()
    finally:
        conn.close()
