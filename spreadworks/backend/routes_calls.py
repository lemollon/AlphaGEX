"""Call history — what Session, Squeeze and Risk actually said, and what SPY did.

Read-only. One endpoint feeds the history panel that hangs under all three
pages, so they share a single definition of "what was the call and was it
right" instead of each page inventing one.

🚨 THIS SERVES THE RECORDED CALLS, NOT RECOMPUTED ONES. The existing
`/risk-advisor/history` re-derives past verdicts from today's code, which means
a threshold change silently rewrites the past and a decaying signal can never
show up. Everything here comes out of `sw_call_log`, which is append-only.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request

from .call_log import (SURFACES, ensure_tables, read_calls, spy_frame,
                       upsert_spy_days)
from .call_scoring import attach_outcomes, disagreements, score

CT = ZoneInfo("America/Chicago")

router = APIRouter(prefix="/api/spreadworks/calls", tags=["Call History"])

# Idempotent, and the one thing that must not be left to import ordering.
ensure_tables()

# Week / month / year, as asked for. `0` means everything held.
RANGE_DAYS = {"week": 7, "month": 31, "year": 365, "all": 3650}

_spy_refreshed: dict[str, datetime] = {}
_SPY_TTL_MIN = 60


async def _refresh_spy(request: Request) -> None:
    """Top up SPY daily bars from Tradier, at most hourly.

    🚨 Stores OPEN as well as close. The existing SPY history caller keeps only
    closes, and the overnight gap - close to the next open - is exactly what a
    call made near the bell has to be scored against.
    """
    now = datetime.now(CT).replace(tzinfo=None)
    last = _spy_refreshed.get("t")
    if last and (now - last).total_seconds() < _SPY_TTL_MIN * 60:
        return
    try:
        from .routes import _tradier_get
        start = (now.date() - timedelta(days=420)).isoformat()
        h = await _tradier_get(request, "/markets/history",
                               {"symbol": "SPY", "interval": "daily",
                                "start": start, "end": now.date().isoformat()})
        days = ((h.get("history") or {}).get("day")) or []
        if isinstance(days, dict):          # Tradier returns a bare dict for n=1
            days = [days]
        if days:
            upsert_spy_days(days)
            _spy_refreshed["t"] = now
    except Exception as e:                  # never break the page over a quote feed
        print(f"[calls] SPY refresh failed ({type(e).__name__})")


@router.get("")
@router.get("/")
async def calls(request: Request,
                surface: Optional[str] = Query(None),
                range: str = Query("month"),
                days: Optional[int] = Query(None)):
    """Every recorded call in the window, with SPY outcomes and honest scoring.

    `range` is week | month | year | all; `days` overrides it.
    """
    if surface and surface not in SURFACES:
        surface = None
    n_days = int(days) if days else RANGE_DAYS.get(range, 31)

    await _refresh_spy(request)

    rows = read_calls(surface=surface, days=n_days)
    spy = spy_frame(days=n_days + 10)
    rows = attach_outcomes(rows, spy)

    # 🚨 THE RISK CALL IS BUILT FROM THE PRIOR CLOSE BY DESIGN. Its data_ts is
    # always ~19h old (yesterday's 15:15 CT close), which every other surface
    # would read as stale. This flag lets the frontend suppress that chip for
    # risk rows instead of the freshness badge crying wolf every single day.
    for r in rows:
        r["structural_lag"] = r.get("surface") == "risk"

    return {
        "surface": surface or "all",
        "range": range,
        "days": n_days,
        "count": len(rows),
        "calls": rows,
        # 🚨 Hit rates ship with the base rate over the SAME days and an n.
        # A 55% hit rate in a market that rises 55% of the time is noise, and
        # without the comparison beside it, it reads as a win.
        "scorecard": score(rows),
        # The days the surfaces split. Two signals that always agree add
        # nothing by being stacked - the disagreements are where the second
        # one earns its keep.
        "disagreements": disagreements(rows),
    }
