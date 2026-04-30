"""Audit replayer -- reconstruct a position's decision chain from audit log.

Given a position_id, fetch all events from goliath_trade_audit (oldest
first) and produce a structured timeline so a human (or downstream
analytics) can review what happened end-to-end.

Use case: post-mortem on a bad trade -- which gate passed, which
trigger fired, what were the inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from . import store


@dataclass
class ReplayedTimeline:
    """The full timeline for one position (or empty if not found)."""

    position_id: str
    instance: Optional[str] = None
    entry_eval: Optional[dict[str, Any]] = None
    entry_filled: Optional[dict[str, Any]] = None
    management_evals: list[dict[str, Any]] = field(default_factory=list)
    exit_filled: Optional[dict[str, Any]] = None

    @property
    def event_count(self) -> int:
        n = 0
        if self.entry_eval is not None:
            n += 1
        if self.entry_filled is not None:
            n += 1
        n += len(self.management_evals)
        if self.exit_filled is not None:
            n += 1
        return n

    @property
    def is_complete(self) -> bool:
        return self.entry_filled is not None and self.exit_filled is not None


def replay_position(position_id: str) -> ReplayedTimeline:
    """Fetch all events for position_id and return a structured timeline."""
    rows = store.query_by_position(position_id)
    timeline = ReplayedTimeline(position_id=position_id)

    for row in rows:
        if timeline.instance is None:
            timeline.instance = row["instance"]

        et = row["event_type"]
        if et == "ENTRY_EVAL":
            timeline.entry_eval = row
        elif et == "ENTRY_FILLED":
            timeline.entry_filled = row
        elif et == "MANAGEMENT_EVAL":
            timeline.management_evals.append(row)
        elif et == "EXIT_FILLED":
            timeline.exit_filled = row
        # Unknown event types are silently skipped; the store CHECK
        # constraint prevents them from being inserted in the first place.

    return timeline


def summarize(timeline: ReplayedTimeline) -> dict[str, Any]:
    """Compact summary suitable for printing or logging."""
    summary: dict[str, Any] = {
        "position_id": timeline.position_id,
        "instance": timeline.instance,
        "event_count": timeline.event_count,
        "is_complete": timeline.is_complete,
        "entry_decision": None,
        "fired_trigger": None,
        "realized_pnl": None,
    }
    if timeline.entry_eval is not None:
        summary["entry_decision"] = timeline.entry_eval.get("data", {}).get("decision")
    if timeline.exit_filled is not None:
        data = timeline.exit_filled.get("data", {})
        summary["fired_trigger"] = data.get("trigger_id")
        summary["realized_pnl"] = data.get("realized_pnl")
    return summary
