"""Squeeze signal API: /api/spreadworks/squeeze

Read-only surface for backend/bots/gamma_regime.py's squeeze_signal — the
current verdict plus enough history for the frontend to chart net gamma and
its own trailing percentile. ADVISORY ONLY: nothing here touches a bot.

The daily capture (15:05 CT) and morning alert (08:05 CT) jobs that keep
sw_gamma_daily fresh live in backend/gamma_alerts.py, registered on the same
scheduler as the Risk Advisor's jobs.

/intraday below is a SEPARATE, purely informational reading: a live chain
pull right now, next to the last stored 15:05 CT close. It is NOT the signal
— sampling at 10:00 CT lands in a different percentile zone than the close
21.6% of the time (495 sessions measured), and ~5% of sessions would flash a
false "oversold" the close then retracts. The frontend must label it that way.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, time as dtime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .bots.gamma_regime import (GAMMA_DAILY_TABLE, PCT_WINDOW, capture_health,
                                data_freshness, job_status, signal_history,
                                signal_summary, squeeze_outlook, squeeze_signal,
                                trade_ticket, vix_history)
from .db import engine as _global_engine

logger = logging.getLogger("spreadworks.routes_squeeze")
router = APIRouter(prefix="/api/spreadworks/squeeze", tags=["Squeeze Signal"])

# Tests override this via monkeypatch (same convention as routes_bots /
# routes_book_risk).
ENGINE: Engine = _global_engine
CT = ZoneInfo("America/Chicago")

HISTORY_ROWS = 90
# The page's range control slices client-side, so /state serves the widest
# window it might ask for in one request rather than refetching per range.
# Capped because _history_with_percentile pulls n + PCT_WINDOW - 1 rows and
# signal_history is O(n * PCT_WINDOW).
MAX_HISTORY_ROWS = 400

# /intraday: 40-ish chain requests per pull, so cache it — same convention as
# routes_bots.py's _FLEET_STATS_CACHE.
_INTRADAY_CACHE: dict[str, Any] = {"ts": 0.0, "payload": None}
_INTRADAY_CACHE_TTL = 60

# RTH-ish window for the "stale" flag. Outside this (or a weekend) the live
# pull is either impossible or meaningless, so the frontend greys it out.
_INTRADAY_OPEN_CT = dtime(8, 30)
_INTRADAY_CLOSE_CT = dtime(15, 0)


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
async def state(sessions: str | None = None):
    """Current squeeze verdict + up to `sessions` sessions of net-gamma
    history (each with its own trailing 60-session percentile) for the
    frontend chart. Never raises — degrades to an UNKNOWN-shaped signal +
    empty history rather than a 500.

    `sessions` is typed as a STRING and parsed here on purpose. Declared as
    `int`, FastAPI's own coercion rejects a non-numeric value with a 422
    before any clamp of ours can run — so `?sessions=abc` blanked the page,
    which is exactly the failure this endpoint's contract exists to prevent.
    It always answers: garbage in, default window out.
    """
    today = datetime.now(CT).date()
    try:
        n_rows = max(1, min(MAX_HISTORY_ROWS, int(sessions)))
    except (TypeError, ValueError):
        n_rows = HISTORY_ROWS
    try:
        sig = squeeze_signal(ENGINE, today)
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze] squeeze_signal failed: %r", e)
        sig = {"verdict": "UNKNOWN", "gamma_pct": None, "net_gex_b": None,
              "vix_ratio": None, "prior_date": None,
              "reason": f"squeeze_signal error: {e}"}
    try:
        history = _history_with_percentile(ENGINE, n=n_rows)
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

    # Freshness. `asof` is the date the DECISION is being made, which is always
    # today — it is NOT a claim about how current the data is, and the page read
    # it as one for as long as it shipped ("As of 2026-08-15" over an 08-11
    # reading). `data_date` is the row the verdict actually came from, and
    # `freshness` is what the page must show when the two disagree.
    try:
        fresh = data_freshness(ENGINE, today)
        for k in ("gamma_date", "vix_date", "expected_date", "last_capture_date"):
            if fresh.get(k) is not None:
                fresh[k] = _isoformat(fresh[k])
        if fresh.get("window_missing"):
            fresh["window_missing"] = [_isoformat(d) for d in fresh["window_missing"]]
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze] data_freshness failed: %r", e)
        fresh = {"reason": f"data_freshness error: {e}", "stale": None}

    # Track record: the verdict each stored session produced, plus a roll-up.
    try:
        sh = signal_history(ENGINE, n=n_rows)
        summary = signal_summary(sh)
        for r in sh:
            r["trade_date"] = _isoformat(r["trade_date"])
        for k in ("last_squeeze_watch", "last_no_sell", "first_date", "last_date"):
            if summary.get(k) is not None:
                summary[k] = _isoformat(summary[k])
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze] signal_history failed: %r", e)
        sh, summary = [], {"reason": f"signal_history error: {e}"}

    # When each scheduled job last actually fired. The page advertised "next
    # capture 15:05 CT" with no way to see that it has never once run.
    try:
        jobs = job_status(ENGINE)
        jobs["last"] = {k: _isoformat(v) if v is not None else None
                        for k, v in (jobs.get("last") or {}).items()}
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze] job_status failed: %r", e)
        jobs = {"last": {}, "reason": f"job_status error: {e}"}
    # ...and whether they are even armed. A dead scheduler and a job that has
    # not fired yet both read as "never run" from the ledger alone.
    try:
        from .gamma_alerts import scheduled_jobs
        jobs["scheduler"] = scheduled_jobs()
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze] scheduled_jobs failed: %r", e)
        jobs["scheduler"] = {"registered": None, "jobs": {},
                             "reason": f"scheduled_jobs error: {e}"}

    # Did the capture claim a slot and store nothing? The dedup ledger records
    # the claim, not the success, so the two must be compared.
    try:
        capture = capture_health(fresh, jobs)
        for k in ("claimed", "stored"):
            if capture.get(k) is not None:
                capture[k] = _isoformat(capture[k])
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze] capture_health failed: %r", e)
        capture = {"state": "unknown", "detail": f"capture_health error: {e}"}

    # The actual strikes. "round(spot) - 2" is a rule; the page has to show
    # numbers or the reader does the arithmetic between here and the order.
    try:
        ticket = trade_ticket(ENGINE, today)
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze] trade_ticket failed: %r", e)
        ticket = {"reason": f"trade_ticket error: {e}"}

    # The forward record: what the signal has actually said since going live,
    # and what happened. Every other number on this page is a backtest.
    try:
        from .bots.squeeze_ledger import ledger_summary
        ledger = ledger_summary(ENGINE)
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze] ledger_summary failed: %r", e)
        ledger = {"reason": f"ledger error: {e}", "rows": []}

    # The VIX leg's own series — it had no history on the page at all.
    try:
        vh = vix_history(ENGINE, n=n_rows)
        for r in vh:
            r["trade_date"] = _isoformat(r["trade_date"])
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze] vix_history failed: %r", e)
        vh = []

    try:
        from .call_log import record_call
        # 🚨 data_ts is the row the verdict CAME FROM, not the moment we asked.
        # The gamma warehouse is ingested by hand, and a stale reading dated as
        # today has already cost a real signal flip - without recording the
        # input's age a bad call and a stale one look identical afterwards.
        _pd = sig.get("prior_date")
        record_call("squeeze", sig.get("verdict"),
                    detail={"gamma_pct": sig.get("gamma_pct"),
                            "net_gex_b": sig.get("net_gex_b"),
                            "vix_ratio": sig.get("vix_ratio"),
                            "stale": (fresh or {}).get("stale")},
                    data_ts=(datetime.combine(_pd, dtime(15, 5))
                             if hasattr(_pd, "year") else None))
    except Exception:
        pass                       # instrumentation never breaks the page

    return {
        "asof": today.isoformat(),
        "data_date": (_isoformat(sig["prior_date"])
                      if sig.get("prior_date") is not None else None),
        "freshness": fresh,
        "jobs": jobs,
        "capture_health": capture,
        "ticket": ticket,
        "ledger": ledger,
        "outlook": outlook,
        "verdict": sig.get("verdict"),
        "gamma_pct": sig.get("gamma_pct"),
        "net_gex_b": sig.get("net_gex_b"),
        "vix_ratio": sig.get("vix_ratio"),
        "prior_date": (_isoformat(sig["prior_date"])
                      if sig.get("prior_date") is not None else None),
        "reason": sig.get("reason"),
        "history": history,
        "vix_history": vh,
        "signal_history": sh,
        "signal_summary": summary,
        "advisory_only": True,
    }


def _pct_if_now(engine: Engine, live_net_gex_b: float) -> float | None:
    """Same trailing-window percentile formula gamma_percentile() uses
    (fraction of the window a value exceeds), applied to a window built from
    the PCT_WINDOW-1 most recently STORED sessions plus the live reading in
    place of "today". Reuses PCT_WINDOW from gamma_regime rather than a
    second constant — do not invent a second window size here."""
    with engine.begin() as conn:
        rows = conn.execute(text(
            f"SELECT net_gex FROM {GAMMA_DAILY_TABLE} ORDER BY trade_date DESC "
            "LIMIT :n"
        ), {"n": PCT_WINDOW - 1}).fetchall()
    if len(rows) < PCT_WINDOW - 1:
        return None
    hist = [float(r[0]) / 1e9 for r in rows] + [live_net_gex_b]
    return sum(1 for v in hist if live_net_gex_b > v) / len(hist)


@router.get("/intraday")
async def intraday():
    """Live SPY net-gamma reading right now — CONTEXT ONLY, NOT THE SIGNAL.

    The shipped signal is one reading a session, captured at 15:05 CT and
    consumed the next morning; it was backtested on that daily close. This
    endpoint pulls the chain live and shows what net gamma looks like THIS
    MINUTE next to that stored close — useful context, not a second verdict.
    Measured against 495 sessions, an intraday sample lands in the wrong
    percentile zone 21.6% of the time versus that session's close, and ~5%
    of sessions would flash a false "oversold" the close then retracts.

    Never raises — degrades to nulls + a `reason` string. Cached 60s
    (module-level) so repeated page loads don't re-pull SPY's full chain
    (~40 requests) every time.
    """
    ts = time.time()
    cached = _INTRADAY_CACHE
    if cached["payload"] is not None and ts - cached["ts"] < _INTRADAY_CACHE_TTL:
        return cached["payload"]

    now = datetime.now(CT)
    stale = now.weekday() >= 5 or not (_INTRADAY_OPEN_CT <= now.time() < _INTRADAY_CLOSE_CT)

    net_gex_b: float | None = None
    spot: float | None = None
    last_close_b: float | None = None
    delta_b: float | None = None
    pct_if_now: float | None = None
    reason: str | None = None

    # DO NOT PULL WHEN THE MARKET IS SHUT. Two reasons, both real:
    #
    #   1. Cost. This is ~40 chain requests. Cached 60s, so an open tab over a
    #      weekend meant 40 Tradier calls a minute, indefinitely, for a number
    #      that cannot change.
    #   2. Honesty. Out of hours Tradier serves the last stale quotes, and the
    #      strip rendered that as "net gamma now $6.30B · +$2.79B vs last
    #      close" — presenting a stale chain differenced against an ORATS
    #      close as though gamma had moved 2.79B. It had not; the market was
    #      closed. The copy even called it "the last available reading", which
    #      it was not: it was a fresh pull of stale quotes taken that second.
    #
    # Serving nulls with a reason is the honest answer. last_close_b below
    # still comes from the database, so the strip keeps its context.
    if stale:
        reason = "market_closed"
    else:
        try:
            from .bots.gamma_regime import fetch_net_gex
            from .bots.routes_helpers import build_live_chain_provider

            def _run() -> dict:
                client = build_live_chain_provider()
                return fetch_net_gex(client, "SPY")

            out = await asyncio.to_thread(_run)
            spot = out.get("spot")
            if out.get("net_gex") is not None:
                net_gex_b = out["net_gex"] / 1e9
            else:
                reason = out.get("reason") or "no_reading"
        except Exception as e:  # noqa: BLE001
            logger.warning("[routes_squeeze] intraday fetch_net_gex failed: %r", e)
            reason = f"fetch_net_gex error: {e}"

    try:
        with ENGINE.begin() as conn:
            row = conn.execute(text(
                f"SELECT net_gex FROM {GAMMA_DAILY_TABLE} "
                "ORDER BY trade_date DESC LIMIT 1"
            )).fetchone()
        if row is not None:
            last_close_b = float(row[0]) / 1e9
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_squeeze] intraday last-close query failed: %r", e)
        if reason is None:
            reason = f"last_close query error: {e}"

    if net_gex_b is not None and last_close_b is not None:
        delta_b = net_gex_b - last_close_b

    if net_gex_b is not None:
        try:
            pct_if_now = _pct_if_now(ENGINE, net_gex_b)
        except Exception as e:  # noqa: BLE001
            logger.warning("[routes_squeeze] intraday pct_if_now failed: %r", e)

    payload = {
        "net_gex_b": net_gex_b,
        "spot": float(spot) if spot else None,
        "captured_at": now.isoformat(),
        "last_close_b": last_close_b,
        "delta_b": delta_b,
        "pct_if_now": pct_if_now,
        "stale": stale,
        "reason": reason,
    }
    _INTRADAY_CACHE["ts"] = ts
    _INTRADAY_CACHE["payload"] = payload
    return payload
