"""Squeeze signal API: /api/spreadworks/squeeze

Read-only surface for backend/bots/gamma_regime.py's squeeze_signal — the
current verdict plus enough history for the frontend to chart net gamma and
its own trailing percentile. ADVISORY ONLY: nothing here touches a bot.

The daily capture (15:05 CT) and morning alert (08:05 CT) jobs that keep
sw_gamma_daily fresh live in backend/gamma_alerts.py, registered on the same
scheduler as the Risk Advisor's jobs.
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .bots.gamma_regime import (GAMMA_DAILY_TABLE, PCT_WINDOW, squeeze_outlook,
                                squeeze_signal)
from .db import engine as _global_engine

logger = logging.getLogger("spreadworks.routes_squeeze")
router = APIRouter(prefix="/api/spreadworks/squeeze", tags=["Squeeze Signal"])

# Tests override this via monkeypatch (same convention as routes_bots /
# routes_book_risk).
ENGINE: Engine = _global_engine
CT = ZoneInfo("America/Chicago")

HISTORY_ROWS = 90


def _isoformat(d) -> str:
    """`d` is a python date on Postgres (native DATE typecasting) but a raw
    string on SQLite when read via a textual query — never crash either way."""
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _history_with_percentile(engine: Engine, n: int = HISTORY_ROWS) -> list[dict]:
    """Last `n` sessions of sw_gamma_daily, each with its OWN trailing
    PCT_WINDOW-session percentile where computable.

    Pulls n + (PCT_WINDOW - 1) extra rows so the percentile for the OLDEST
    row in the returned window can still be computed from its own trailing
    history, then trims back down to `n` for the response.
    """
    fetch_n = n + PCT_WINDOW - 1
    with engine.begin() as conn:
        rows = conn.execute(text(
            f"SELECT trade_date, net_gex, spot FROM {GAMMA_DAILY_TABLE} "
            "ORDER BY trade_date DESC LIMIT :n"
        ), {"n": fetch_n}).fetchall()
    rows = sorted(rows, key=lambda r: r[0])   # ascending by trade_date

    out = []
    for i, (d, net_gex, spot) in enumerate(rows):
        window = rows[max(0, i - PCT_WINDOW + 1):i + 1]
        pct = None
        if len(window) >= PCT_WINDOW:
            vals = [float(w[1]) for w in window]
            pct = sum(1 for v in vals if float(net_gex) > v) / len(vals)
        out.append({
            "trade_date": _isoformat(d),
            "net_gex_b": float(net_gex) / 1e9,
            "spot": float(spot) if spot is not None else None,
            "pct": pct,
        })
    return out[-n:]


@router.get("/state")
async def state():
    """Current squeeze verdict + up to 90 sessions of net-gamma history
    (each with its own trailing 60-session percentile) for the frontend
    chart. Never raises — degrades to an UNKNOWN-shaped signal + empty
    history rather than a 500."""
    today = datetime.now(CT).date()
    try:
        sig = squeeze_signal(ENGINE, today)
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze] squeeze_signal failed: %r", e)
        sig = {"verdict": "UNKNOWN", "gamma_pct": None, "net_gex_b": None,
              "vix_ratio": None, "prior_date": None,
              "reason": f"squeeze_signal error: {e}"}
    try:
        history = _history_with_percentile(ENGINE)
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze] history query failed: %r", e)
        history = []

    # Trigger LEVELS, not just the verdict — a verdict says nothing until the
    # day it flips, so surface what gamma would have to print to cross, which
    # way it is travelling, and which leg of SQUEEZE_WATCH is still missing.
    try:
        outlook = squeeze_outlook(ENGINE, today)
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze] squeeze_outlook failed: %r", e)
        outlook = {"reason": f"squeeze_outlook error: {e}"}

    return {
        "asof": today.isoformat(),
        "outlook": outlook,
        "verdict": sig.get("verdict"),
        "gamma_pct": sig.get("gamma_pct"),
        "net_gex_b": sig.get("net_gex_b"),
        "vix_ratio": sig.get("vix_ratio"),
        "prior_date": (_isoformat(sig["prior_date"])
                      if sig.get("prior_date") is not None else None),
        "reason": sig.get("reason"),
        "history": history,
        "advisory_only": True,
    }
