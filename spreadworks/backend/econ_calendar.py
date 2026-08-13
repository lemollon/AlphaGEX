"""Macro-event calendar for 2026 — SOURCED, never typed from memory.

Fetched 2026-08-13 from the OFFICIAL publishers:
  * FOMC:  https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
           (decision day = second day of each two-day meeting)
  * CPI:   https://www.bls.gov/schedule/news_release/cpi.htm   (08:30 ET)
  * NFP:   https://www.bls.gov/schedule/news_release/empsit.htm (08:30 ET,
           Employment Situation)

Context only: the literature (Gao et al. 2018 §8.3) says intraday behavior
differs on macro-announcement days, so the page/alerts SHOW the fact. No
signal on this page changes because of it — that would need its own
pre-registered trial. Refresh this file each December from the same URLs.
"""
from __future__ import annotations

from datetime import date, timedelta

MACRO_2026: dict[date, str] = {}


def _add(label: str, dates: list[tuple[int, int]]) -> None:
    for m, d in dates:
        k = date(2026, m, d)
        MACRO_2026[k] = f"{MACRO_2026[k]} + {label}" if k in MACRO_2026 else label


_add("FOMC decision", [(1, 28), (3, 18), (4, 29), (6, 17), (7, 29), (9, 16),
                       (10, 28), (12, 9)])
_add("CPI release", [(1, 13), (2, 13), (3, 11), (4, 10), (5, 12), (6, 10),
                     (7, 14), (8, 12), (9, 11), (10, 14), (11, 10), (12, 10)])
_add("Jobs report (NFP)", [(1, 9), (2, 11), (3, 6), (4, 3), (5, 8), (6, 5),
                           (7, 2), (8, 7), (9, 4), (10, 2), (11, 6), (12, 4)])


def macro_today(d: date) -> str | None:
    """Label if `d` is a macro-announcement day, else None."""
    return MACRO_2026.get(d)


def next_macro(d: date, horizon_days: int = 30) -> dict | None:
    """The next macro event strictly after `d` within the horizon."""
    for i in range(1, horizon_days + 1):
        k = d + timedelta(days=i)
        if k in MACRO_2026:
            return {"d": k.isoformat(), "label": MACRO_2026[k]}
    return None
