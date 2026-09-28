"""Intraday curve-refresh shortlist (2026-09-28 daily-cache redesign -- see PR after #3106).
Extracted to its own module (same split as ember_lock.py / rate_limiter.py) so the selection
rule itself is unit-testable without importing tv_scanner.py, which executes its scan
top-level on import with no __main__ guard.

Redesign summary (tv_scanner.py's module docstring, sections B/CONCURRENCY, has the full
version): a scheduled DAILY FULL PASS (--daily-curves, ~07:55 CT, its own ~35-min timeout, no
broker lock) pre-warms the per-name GEX curve cache for the whole ~150-name universe once a
day. Regular intraday --live ticks (every 30 min) then reuse that day's cached curve for most
names -- the dealer positioning structure it captures doesn't need a fresh network hit every
30 minutes -- and only pay the expensive (5-calls/min) curve endpoint again for a SHORTLIST of
names actually near a setup, where a stale curve is more likely to matter. This module answers
one question: which names are on that shortlist.

SHORTLIST RULE: a ticker is "near a setup" if the scanner's own EXISTING ledger already scored
it >=1:1 RR on today's session (any row in tools/ember_ledger.jsonl for today's scan_date --
setup/marginal/illiquid on either strategy; HIDDEN rows are never ledgered by tv_scanner.py, so
they're excluded automatically, no new threshold invented here). If today's ledger has nothing
yet (first tick of the day, before any run has scored anything), fall back to today's freshly
built candidate list's own opportunity_score-desc ordering (the same ranking tv_scanner.py's
wall-clock truncation already uses) and take the top-ranked names. Either way, capped at
`max_size` (tv_scanner.py passes SHORTLIST_MAX=15) so a shortlist-only intraday tick's curve
refetches stay comfortably inside a 2-4 minute budget under the 5-expensive-calls/min limit.
"""
from __future__ import annotations

from typing import Iterable


def build_shortlist(
    ledger_rows: Iterable[dict],
    today_scan_date: str,
    ranked_tickers: list[str],
    max_size: int,
) -> set[str]:
    """`ledger_rows` -- every row already parsed from tools/ember_ledger.jsonl (dicts with at
    least "ticker" and "scan_date"; malformed/irrelevant rows are the caller's problem, this
    function only reads the two keys it needs and tolerates them being absent).
    `today_scan_date` -- str(sess), the session date tv_scanner.py's own rows are keyed on.
    `ranked_tickers` -- today's candidate tickers in opportunity_score-desc order (the same
    order tv_scanner.py's `candidates` list is already sorted into before dispatch).
    `max_size` -- hard cap on the returned set's size.
    Never raises: a malformed row is skipped, not fatal."""
    near_setup: set[str] = set()
    for row in ledger_rows:
        try:
            if row.get("scan_date") == today_scan_date and row.get("ticker"):
                near_setup.add(row["ticker"])
        except AttributeError:
            continue

    if not near_setup:
        return set(ranked_tickers[:max_size])

    if len(near_setup) > max_size:
        ranked_in_shortlist = [t for t in ranked_tickers if t in near_setup]
        # ranked_tickers is every candidate; near_setup may reference a ticker no longer in
        # today's candidate list (e.g. it dropped off every source list this tick) -- keep
        # those at the end, order among themselves doesn't matter, the cap still applies.
        leftover = [t for t in near_setup if t not in ranked_tickers]
        near_setup = set((ranked_in_shortlist + leftover)[:max_size])

    return near_setup
