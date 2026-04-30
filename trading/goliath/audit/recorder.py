"""Audit recorder -- convenience wrappers over audit.store.insert.

One method per event type so callers don't open-code event_type strings
or the data-dict shape. Each method is best-effort: returns True on
successful persist, False on DB failure.
"""
from __future__ import annotations

from typing import Any, Optional

from . import store


def record_entry_eval(
    instance: str,
    chain: list[dict[str, Any]],
    structure: Optional[dict[str, Any]],
    decision: str,  # "STRUCTURE_RETURNED" or "FAILED_AT:<gate>"
    position_id: Optional[str] = None,
) -> bool:
    """Persist an ENTRY_EVAL event covering the full gate chain.

    chain: list of {gate, outcome, reason, context}
    structure: serialized TradeStructure (None when no entry produced)
    """
    return store.insert(
        instance=instance,
        event_type="ENTRY_EVAL",
        data={"chain": chain, "structure": structure, "decision": decision},
        position_id=position_id,
    )


def record_entry_filled(
    instance: str,
    position_id: str,
    structure: dict[str, Any],
    fill_details: dict[str, Any],
    contracts: int,
) -> bool:
    """Persist an ENTRY_FILLED event after broker confirms all 3 legs."""
    return store.insert(
        instance=instance,
        event_type="ENTRY_FILLED",
        data={
            "structure": structure,
            "fill_details": fill_details,
            "contracts": contracts,
        },
        position_id=position_id,
    )


def record_management_eval(
    instance: str,
    position_id: str,
    triggers_evaluated: list[str],
    fired_action: Optional[dict[str, Any]],
    position_snapshot: dict[str, Any],
) -> bool:
    """Persist a MANAGEMENT_EVAL event with which trigger fired (or none)."""
    return store.insert(
        instance=instance,
        event_type="MANAGEMENT_EVAL",
        data={
            "triggers_evaluated": triggers_evaluated,
            "fired_action": fired_action,
            "position_snapshot": position_snapshot,
        },
        position_id=position_id,
    )


def record_exit_filled(
    instance: str,
    position_id: str,
    trigger_id: str,
    legs_closed: list[str],
    realized_pnl: float,
    fill_details: dict[str, Any],
) -> bool:
    """Persist an EXIT_FILLED event after broker confirms the close legs."""
    return store.insert(
        instance=instance,
        event_type="EXIT_FILLED",
        data={
            "trigger_id": trigger_id,
            "legs_closed": legs_closed,
            "realized_pnl": realized_pnl,
            "fill_details": fill_details,
        },
        position_id=position_id,
    )
