"""GOLIATH paper-trading broker executor.

Per Q4 + paper-trading direction (2026-05-01): no real Tradier execution.
This executor simulates fills at the current Tradier mid-prices and
persists positions to goliath_paper_positions (migration 032).

Lifecycle:
    Engine returns approved EngineEntryDecision -> paper_broker_executor()
    is called by Runner.run_entry_cycle. We:
      1. Generate a UUID position_id
      2. INSERT a goliath_paper_positions row with all entry economics
      3. Record audit event ENTRY_FILLED via Phase 6 recorder
      4. Append the position to instance.open_positions so management
         cycles see it
      5. Return position_id (Runner uses it to fire Discord OPEN alert)

Returns None on persistence failure (Runner skips the alert).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from trading.goliath.audit import recorder as audit_recorder
from trading.goliath.engine import EngineEntryDecision
from trading.goliath.instance import GoliathInstance
from trading.goliath.management.state import Position, PositionState

logger = logging.getLogger(__name__)


def _connect():
    try:
        from database_adapter import get_connection, is_database_available  # type: ignore
    except ImportError:
        return None, False
    if not is_database_available():
        return None, False
    try:
        return get_connection(), True
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper_executor DB connect failed: %r", exc)
        return None, False


def _next_friday(now: Optional[datetime] = None) -> date:
    """Spec section 1.7: 7 DTE means same-week Friday. Cap to next-Friday
    if entered after Friday."""
    if now is None:
        now = datetime.now(timezone.utc)
    today = now.date()
    # weekday(): Monday=0, Friday=4
    days_to_fri = (4 - today.weekday()) % 7
    if days_to_fri == 0 and now.hour >= 16:  # after market close on Friday
        days_to_fri = 7
    return today + timedelta(days=days_to_fri)


def _persist_position(
    position_id: str,
    instance: GoliathInstance,
    decision: EngineEntryDecision,
    expiration: date,
) -> bool:
    """INSERT row into goliath_paper_positions. Returns True on success."""
    s = decision.structure
    if s is None:
        return False

    sp_mid = (s.short_put.bid + s.short_put.ask) / 2.0
    lp_mid = (s.long_put.bid + s.long_put.ask) / 2.0
    lc_mid = (s.long_call.bid + s.long_call.ask) / 2.0
    spread_width = s.short_put.strike - s.long_put.strike
    defined_max_loss = spread_width - s.put_spread_credit
    entry_underlying_regime = "POSITIVE"  # v0.2 placeholder; v0.3 reads from snapshot

    conn, ok = _connect()
    if not ok or conn is None:
        return False
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO goliath_paper_positions (
                    position_id, instance_name, letf_ticker, underlying_ticker,
                    state, opened_at, expiration_date,
                    short_put_strike, long_put_strike, long_call_strike,
                    contracts,
                    entry_short_put_mid, entry_long_put_mid, entry_long_call_mid,
                    entry_put_spread_credit, entry_long_call_cost, entry_net_cost,
                    defined_max_loss, entry_underlying_gex_regime
                ) VALUES (
                    %s, %s, %s, %s,
                    'OPEN', NOW(), %s,
                    %s, %s, %s,
                    %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s
                )
                """,
                (
                    position_id, instance.name, instance.letf_ticker, instance.underlying_ticker,
                    expiration,
                    s.short_put.strike, s.long_put.strike, s.long_call.strike,
                    decision.contracts_to_trade,
                    sp_mid, lp_mid, lc_mid,
                    s.put_spread_credit, s.long_call_cost, s.net_cost,
                    defined_max_loss, entry_underlying_regime,
                ),
            )
            conn.commit()
            return True
        finally:
            cur.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper_executor insert failed for %s: %r", position_id, exc)
        return False
    finally:
        conn.close()


def _structure_to_jsonable(decision: EngineEntryDecision) -> dict:
    s = decision.structure
    return {
        "short_put_strike": s.short_put.strike,
        "long_put_strike": s.long_put.strike,
        "long_call_strike": s.long_call.strike,
        "put_spread_credit": s.put_spread_credit,
        "long_call_cost": s.long_call_cost,
        "net_cost": s.net_cost,
    }


def paper_broker_executor(
    instance: GoliathInstance,
    decision: EngineEntryDecision,
) -> Optional[str]:
    """Simulate a fill and return a position_id, or None on persistence failure.

    Wired into Runner via Runner(broker_executor=paper_broker_executor).
    """
    if not decision.approved or decision.structure is None:
        return None

    position_id = f"goliath-paper-{uuid.uuid4().hex[:12]}"
    expiration = _next_friday()

    persisted = _persist_position(position_id, instance, decision, expiration)
    if not persisted:
        logger.warning("paper_executor: failed to persist %s; skipping fill", position_id)
        return None

    # Build a Position for in-memory management cycles. The runner appends
    # this to instance.open_positions so subsequent management cycles
    # evaluate triggers against it.
    s = decision.structure
    sp_mid = (s.short_put.bid + s.short_put.ask) / 2.0
    lp_mid = (s.long_put.bid + s.long_put.ask) / 2.0
    lc_mid = (s.long_call.bid + s.long_call.ask) / 2.0
    spread_width = s.short_put.strike - s.long_put.strike
    defined_max_loss = spread_width - s.put_spread_credit

    pos = Position(
        position_id=position_id,
        instance_name=instance.name,
        letf_ticker=instance.letf_ticker,
        underlying_ticker=instance.underlying_ticker,
        state=PositionState.OPEN,
        entered_at=datetime.now(timezone.utc),
        expiration_date=expiration,
        short_put_strike=s.short_put.strike,
        long_put_strike=s.long_put.strike,
        long_call_strike=s.long_call.strike,
        entry_long_call_cost=s.long_call_cost,
        entry_put_spread_credit=s.put_spread_credit,
        entry_net_cost=s.net_cost,
        defined_max_loss=defined_max_loss,
        entry_underlying_gex_regime="POSITIVE",
        current_short_put_mid=sp_mid,
        current_long_put_mid=lp_mid,
        current_long_call_mid=lc_mid,
        current_underlying_spot=0.0,  # filled in next management cycle
        current_underlying_gex_regime="POSITIVE",
    )
    instance.add_position(pos)

    # Audit ENTRY_FILLED.
    audit_recorder.record_entry_filled(
        instance=instance.name,
        position_id=position_id,
        structure=_structure_to_jsonable(decision),
        fill_details={
            "mode": "paper",
            "fill_basis": "tradier_mid",
            "sp_fill": sp_mid,
            "lp_fill": lp_mid,
            "lc_fill": lc_mid,
        },
        contracts=decision.contracts_to_trade,
    )

    return position_id
