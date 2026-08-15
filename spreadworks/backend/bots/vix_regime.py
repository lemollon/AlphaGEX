"""VIX decay ratio — the one regime gate that survived a blind OOS decade.

WHAT IT MEASURES
----------------
    ratio = VIX(prior session) / max(VIX over the 20 sessions before that)

Not the LEVEL of fear — whether the spike has ALREADY HAPPENED. Near 1.0 means
fear is peaking and still building; below ~0.9 means a spike is decaying and the
tape is calming down. Short-premium bots want the decaying side.

WHY THE LAG IS NOT OPTIONAL
---------------------------
The numerator is the PRIOR session's VIX close, never today's. Today's close is
not knowable at a 13:05 CT entry, and conditioning on it is conditioning on the
day's own outcome. Measured on EBB's 13:05 stream (930 real-NBBO trades):

    always on                        $+4.60/trade   ret/DD 6.72
    same-day ratio  (LOOK-AHEAD)     $+9.44/trade   ret/DD 13.64   <- not real
    prior-session ratio (TRADEABLE)  $+6.51/trade   ret/DD 7.38    <- this

The look-ahead version was worth roughly double the honest one. That gap is the
whole reason this module reads history and never today.

EXPECTATIONS, HONESTLY
----------------------
On the untouched last third the gate takes EBB's PM tranche from $+1.78 to
$+3.04/trade (t = +0.89 — an improvement, NOT a significant one on its own).
Every calendar year is positive under it: 2022 +$385 / 2023 +$949 / 2024 +$1,386
/ 2025 +$1,266 / 2026 +$302, against −$55 for 2026 ungated. Treat it as a modest,
consistent tilt that also rescues the flat year — not as a proven signal.

UNKNOWN IS NOT "SAFE"
---------------------
With fewer than 21 prior sessions on file the ratio is undefined and this module
returns None. Callers must treat None as BLOCK, not as pass. A veto whose data is
missing must not silently degrade into always-on trading on precisely the days
data tends to be missing.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

# Sessions in the trailing-max window, and how many prior rows we need before
# the ratio is defined at all (window + the prior session itself).
WINDOW = 20
MIN_HISTORY = WINDOW + 1

VIX_DAILY_TABLE = "sw_vix_daily"

_VIX_DDL = f"""
CREATE TABLE IF NOT EXISTS {VIX_DAILY_TABLE} (
    trade_date  DATE PRIMARY KEY,
    vix         NUMERIC(8,2) NOT NULL,
    updated_at  TIMESTAMP NOT NULL
)
"""


def ensure_vix_table(engine: Engine) -> None:
    """Idempotent create. Safe to call every scan cycle."""
    with engine.begin() as conn:
        conn.execute(text(_VIX_DDL))


def record_vix(engine: Engine, trade_date: date, vix: float) -> None:
    """Upsert one session's VIX.

    The scanner calls this each cycle with the live VIX spot, so the row for
    today is overwritten repeatedly and settles on roughly the close (the scan
    loop runs to 14:59 CT). That intraday churn is harmless: the ratio only ever
    reads sessions STRICTLY BEFORE the day being judged, so today's own row can
    never influence today's decision.
    """
    if vix is None or float(vix) <= 0:
        return
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            conn.execute(text(
                f"INSERT INTO {VIX_DAILY_TABLE} (trade_date, vix, updated_at) "
                "VALUES (:d, :v, CURRENT_TIMESTAMP) "
                "ON CONFLICT(trade_date) DO UPDATE SET "
                "vix = excluded.vix, updated_at = CURRENT_TIMESTAMP"
            ), {"d": trade_date, "v": float(vix)})
        else:
            conn.execute(text(
                f"INSERT INTO {VIX_DAILY_TABLE} (trade_date, vix, updated_at) "
                "VALUES (:d, :v, NOW()) "
                "ON CONFLICT (trade_date) DO UPDATE SET "
                "vix = EXCLUDED.vix, updated_at = NOW()"
            ), {"d": trade_date, "v": float(vix)})


def vix_decay_ratio(engine: Engine, asof: date) -> dict[str, Any]:
    """Ratio for a decision being made ON `asof`, using only prior sessions.

    Returns {"ratio": float|None, "prior_date", "prior_vix", "window_max",
             "n_history", "reason": str|None}. ratio is None when there is not
            enough history — callers must block, not pass.
    """
    with engine.begin() as conn:
        rows = conn.execute(text(
            f"SELECT trade_date, vix FROM {VIX_DAILY_TABLE} "
            "WHERE trade_date < :d ORDER BY trade_date DESC LIMIT :n"
        ), {"d": asof, "n": MIN_HISTORY}).fetchall()

    if len(rows) < MIN_HISTORY:
        return {"ratio": None, "prior_date": None, "prior_vix": None,
                "window_max": None, "n_history": len(rows),
                "reason": f"insufficient_vix_history: have={len(rows)} need={MIN_HISTORY}"}

    # rows[0] is the prior session; rows[1:] are the 20 sessions before it.
    prior_date, prior_vix = rows[0][0], float(rows[0][1])
    window = [float(r[1]) for r in rows[1:]]
    window_max = max(window)
    if window_max <= 0:
        return {"ratio": None, "prior_date": prior_date, "prior_vix": prior_vix,
                "window_max": window_max, "n_history": len(rows),
                "reason": "bad_vix_window_max"}

    return {"ratio": prior_vix / window_max, "prior_date": prior_date,
            "prior_vix": prior_vix, "window_max": window_max,
            "n_history": len(rows), "reason": None}
