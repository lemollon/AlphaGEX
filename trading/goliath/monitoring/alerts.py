"""GOLIATH alert threshold checks + composer.

Per master spec section 10.2, GOLIATH should alert on:
    - heartbeat missed > 3 min
    - TV API failures > 3 in 10 min
    - yfinance failures > 5 in 10 min
    - token expiry < 7 days
    - position drift
    - order rejection
    - day's drawdown > 1.5%% (warn) or > 3%% (page)

v1 implementation (this module): heartbeat staleness, TV/yfinance
failure rate, kill-switch fires. v0.3+ items (drawdown, position
drift, token expiry, order rejection) need P&L and broker-state
infrastructure that lands with later phases.

All alert posts are best-effort; Discord failures never block trading.
The failure-rate counters are simple in-memory windows so each runner
process tracks its own. Cross-process aggregation is a v0.3 concern.
"""
from __future__ import annotations

import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Optional

from . import discord, heartbeat

logger = logging.getLogger(__name__)


# ---- Failure-rate windows -----------------------------------------------

@dataclass
class _RateWindow:
    """Track failure timestamps over a rolling time window."""

    seconds: int
    threshold: int
    events: deque = None

    def __post_init__(self):
        if self.events is None:
            self.events = deque()

    def record(self, now: Optional[float] = None) -> None:
        ts = now if now is not None else time.time()
        self.events.append(ts)
        self._evict(ts)

    def count(self, now: Optional[float] = None) -> int:
        ts = now if now is not None else time.time()
        self._evict(ts)
        return len(self.events)

    def breached(self, now: Optional[float] = None) -> bool:
        return self.count(now) > self.threshold

    def _evict(self, now: float) -> None:
        cutoff = now - self.seconds
        while self.events and self.events[0] < cutoff:
            self.events.popleft()


# Module-global counters (per-process). Tests can replace these.
TV_API_FAILURES = _RateWindow(seconds=600, threshold=3)
YFINANCE_FAILURES = _RateWindow(seconds=600, threshold=5)


def record_tv_api_failure() -> None:
    TV_API_FAILURES.record()


def record_yfinance_failure() -> None:
    YFINANCE_FAILURES.record()


# ---- Threshold checks ----------------------------------------------------

def check_heartbeat_stale(bot_name: str, max_age_seconds: int = 300) -> bool:
    """True when heartbeat is missing or stale. Caller decides whether
    to fire an alert -- this only computes the predicate."""
    return heartbeat.is_stale(bot_name, max_age_seconds=max_age_seconds)


def check_tv_api_failure_rate() -> bool:
    """True when TV API failures exceed threshold (>3 in 10 min)."""
    return TV_API_FAILURES.breached()


def check_yfinance_failure_rate() -> bool:
    """True when yfinance failures exceed threshold (>5 in 10 min)."""
    return YFINANCE_FAILURES.breached()


# ---- Alert composers (call discord.post_embed inside) -------------------

def alert_heartbeat_stale(bot_name: str) -> bool:
    """Post a WARN alert that bot_name's heartbeat is stale."""
    embed = discord.build_alert_embed(
        severity="WARN",
        title="Heartbeat stale",
        description=(
            f"{bot_name} has not written a heartbeat in over 5 minutes. "
            "Check Render service status and worker logs."
        ),
        fields=[{"name": "Bot", "value": bot_name, "inline": True}],
    )
    return discord.post_embed(**embed)


def alert_tv_api_failures() -> bool:
    embed = discord.build_alert_embed(
        severity="WARN",
        title="TV API failure rate exceeded",
        description=(
            f"More than {TV_API_FAILURES.threshold} TV API failures in the "
            f"last {TV_API_FAILURES.seconds // 60} minutes. Check token "
            "validity and TV service status."
        ),
        fields=[
            {"name": "Failures (window)",
             "value": str(TV_API_FAILURES.count()),
             "inline": True},
        ],
    )
    return discord.post_embed(**embed)


def alert_yfinance_failures() -> bool:
    embed = discord.build_alert_embed(
        severity="WARN",
        title="yfinance failure rate exceeded",
        description=(
            f"More than {YFINANCE_FAILURES.threshold} yfinance failures in "
            f"the last {YFINANCE_FAILURES.seconds // 60} minutes. Check "
            "Yahoo rate-limit status; consider extending retry backoff."
        ),
        fields=[
            {"name": "Failures (window)",
             "value": str(YFINANCE_FAILURES.count()),
             "inline": True},
        ],
    )
    return discord.post_embed(**embed)


def alert_kill_switch(
    scope: str,
    instance: Optional[str],
    trigger_id: str,
    reason: str,
) -> bool:
    """Post a kill-switch fire alert. Use the kill-specific embed builder
    (purple color, distinct from generic alerts)."""
    embed = discord.build_kill_embed(scope, instance, trigger_id, reason)
    return discord.post_embed(**embed)


def alert_entry_filled(
    instance: str,
    structure: dict[str, Any],
    contracts: int,
) -> bool:
    """Post an OPEN-event embed."""
    embed = discord.build_entry_embed(instance, structure, contracts)
    return discord.post_embed(**embed)


def alert_exit_filled(
    instance: str,
    trigger_id: str,
    realized_pnl: float,
    legs_closed: list[str],
) -> bool:
    """Post a CLOSE-event embed."""
    embed = discord.build_exit_embed(instance, trigger_id, realized_pnl, legs_closed)
    return discord.post_embed(**embed)
