"""An immutable record of every call the Session, Squeeze and Risk pages made.

WHY THIS EXISTS AT ALL
----------------------
🚨 THE THREE PAGES DID NOT KEEP A HISTORY - THEY RECOMPUTED ONE.

`/risk-advisor/history` loops over past dates and re-derives the action and
headline from today's code. Squeeze does the same, re-scoring `sw_gamma_daily`
against a trailing percentile on every request. That looks like history and is
not: **change a threshold tomorrow and every past "verdict" silently changes
with it.** A scorecard built on that measures the current code against the past,
not the calls that were actually made, and it can never show a signal decaying -
the old calls keep getting rewritten to agree with the new rules.

So this table records what was SHOWN, when it was shown, and never touches it
again.

🚨 AND INTRADAY FLIPS WERE BEING LOST. `risk_confirm_state` is keyed on the
date alone, so a second call the same day overwrites the first. Leron asked for
every call "even if the recommendation changes multiple times a day", and that
was impossible to answer from the existing tables.

WHAT COUNTS AS A CALL
---------------------
A row is written only when the verdict CHANGES. Sampling every fifteen minutes
and storing all of it would be 26 identical rows a day per surface, and the
question being asked is "when did it flip", not "what was it at 10:45".

THE TWO TIMESTAMPS ARE NOT THE SAME THING
-----------------------------------------
🚨 `call_ts` is when we observed the verdict; `data_ts` is how fresh the INPUT
was. The squeeze warehouse is ingested by hand, and a stale reading dated as
today has already cost a real signal flip once. Without both, a bad call and a
stale call are indistinguishable afterwards - which is precisely when you need
to tell them apart.

Everything is stamped in CT because the trading day is a CT concept: a 19:00 CT
observation is tomorrow in UTC and would file itself one row away from its own
outcome.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import (BigInteger, Column, Date, DateTime, Float, Index,
                        Integer, String, Text, desc)

from .db import Base, SessionLocal

CT = ZoneInfo("America/Chicago")

SURFACES = ("session", "squeeze", "risk")

# 🚨 The pre-open placeholder Session writes before the 10:00 snapshot exists.
# Named here so `routes_calls` can drop it from the table/scorecard on days a
# real 10:15 call landed, without hardcoding the string a second place.
PLACEHOLDER_SESSION_VERDICT = "WAITING FOR THE 10:00 SNAPSHOT"

# The literal strings each surface can show. Kept here so a typo in a caller
# fails loudly instead of quietly creating a fourth verdict nobody scores.
KNOWN_VERDICTS = {
    "squeeze": {"SQUEEZE_WATCH", "NO_SELL", "SELL_PREMIUM", "NEUTRAL", "UNKNOWN"},
    "risk": {"stand_down", "skip_entry", "normal"},
    "session": {"DOWN CONFIRMED", "UP CONFIRMED", "ARMED — WAITING FOR A SIDE",
                "NOT ARMED", PLACEHOLDER_SESSION_VERDICT},
}


class CallLog(Base):
    """One row per CHANGE of verdict, per surface. Append-only, never updated."""

    __tablename__ = "sw_call_log"

    # 🚨 BIGINT does not autoincrement on SQLite - only INTEGER PRIMARY KEY
    # does - and every insert failed with an IntegrityError under the test
    # database while working fine on Postgres. The variant keeps BIGINT in
    # production and degrades to INTEGER locally.
    id = Column(BigInteger().with_variant(Integer, "sqlite"),
                primary_key=True, autoincrement=True)
    surface = Column(String(16), nullable=False)
    trade_date = Column(Date, nullable=False)       # CT trading day
    call_ts = Column(DateTime, nullable=False)      # CT wall clock, when observed
    verdict = Column(String(64), nullable=False)
    detail = Column(Text)                           # JSON: the numbers behind it
    data_ts = Column(DateTime)                      # freshness of the INPUT


Index("ix_sw_call_log_surface_date", CallLog.surface, CallLog.trade_date)


class SpyDaily(Base):
    """SPY daily bars, so a call can be scored against what actually happened.

    🚨 THE OPEN IS THE POINT. `sw_gamma_daily.spot` already holds a close, but
    nothing stored an OPEN, and the overnight gap - close to the NEXT open - is
    the window that matters for a call made near the bell. Tradier's daily
    history already returns open/high/low/close; the existing caller just threw
    everything but the close away.
    """

    __tablename__ = "sw_spy_daily"

    trade_date = Column(Date, primary_key=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)


def ensure_tables() -> None:
    """Create these two tables if they are missing.

    🚨 THE REPO HAS BEEN BITTEN BY THIS EXACT ORDERING BEFORE - see the note in
    signal_calibration.py. `Base.metadata.create_all()` runs inside the app
    lifespan, and anything imported lazily (from inside an endpoint) is NOT on
    the metadata when it fires. On a cold database that table then never
    exists, every write fails, and because the writes are deliberately
    fail-soft it happens in complete silence.

    routes_calls imports this module at app-import time, which is before the
    lifespan runs, so the ordering is currently fine. This is belt and braces
    for the day someone changes that - it is idempotent and costs one query at
    boot.
    """
    try:
        from .db import engine
        if engine is not None:
            Base.metadata.create_all(
                bind=engine, tables=[CallLog.__table__, SpyDaily.__table__])
    except Exception as e:                            # noqa: BLE001
        print(f"[call_log] table create failed ({type(e).__name__})")


def _now_ct() -> datetime:
    return datetime.now(CT).replace(tzinfo=None)


def latest_call(surface: str) -> Optional[CallLog]:
    """The most recent call for a surface, or None."""
    if SessionLocal is None:
        return None
    db = SessionLocal()
    try:
        return (db.query(CallLog)
                  .filter(CallLog.surface == surface)
                  .order_by(desc(CallLog.call_ts), desc(CallLog.id))
                  .first())
    except Exception:
        return None
    finally:
        db.close()


def record_call(surface: str, verdict: Optional[str],
                detail: Optional[dict[str, Any]] = None,
                data_ts: Optional[datetime] = None,
                now: Optional[datetime] = None) -> bool:
    """Append a call if it DIFFERS from the last one. True when a row was written.

    🚨 Never raises. This is instrumentation hanging off endpoints that have a
    job to do; a logging failure must not take a page down with it.
    """
    if SessionLocal is None or surface not in SURFACES:
        return False
    if not verdict:
        return False                     # "no opinion yet" is not a call
    known = KNOWN_VERDICTS.get(surface)
    if known and verdict not in known:
        # Loud in the log, but still recorded - an unexpected verdict is
        # exactly the thing you want a history of.
        print(f"[call_log] unknown {surface} verdict {verdict!r}")

    ts = now or _now_ct()
    db = SessionLocal()
    try:
        prev = (db.query(CallLog)
                  .filter(CallLog.surface == surface)
                  .order_by(desc(CallLog.call_ts), desc(CallLog.id))
                  .first())
        # 🚨 Skipping on "same verdict as the last row EVER" meant a steady
        # NORMAL never wrote again once it had written once - one row since
        # 8/19. The dedupe is meant to collapse repeat polling WITHIN a
        # session, not across every session forever. Comparing trade_date
        # too gives one row per session (the first call of the day) plus
        # every same-day flip, which is what "when did it flip" needs.
        if (prev is not None and prev.verdict == verdict
                and prev.trade_date == ts.date()):
            return False                 # unchanged today - not a new call
        db.add(CallLog(surface=surface, trade_date=ts.date(), call_ts=ts,
                       verdict=verdict,
                       detail=json.dumps(detail or {}, default=str)[:4000],
                       data_ts=data_ts))
        db.commit()
        return True
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[call_log] record failed ({type(e).__name__}) - not fatal")
        return False
    finally:
        db.close()


def read_calls(surface: Optional[str] = None, days: int = 90,
               now: Optional[datetime] = None) -> list[dict]:
    """Calls newest-first, optionally for one surface."""
    if SessionLocal is None:
        return []
    ts = now or _now_ct()
    since = ts.date() - timedelta(days=max(1, int(days)))
    db = SessionLocal()
    try:
        q = db.query(CallLog).filter(CallLog.trade_date >= since)
        if surface and surface in SURFACES:
            q = q.filter(CallLog.surface == surface)
        rows = q.order_by(desc(CallLog.call_ts), desc(CallLog.id)).all()
        out = []
        for r in rows:
            try:
                det = json.loads(r.detail) if r.detail else {}
            except Exception:
                det = {}
            out.append({
                "id": r.id,
                "surface": r.surface,
                "trade_date": r.trade_date.isoformat() if r.trade_date else None,
                "call_ts": r.call_ts.isoformat() if r.call_ts else None,
                "verdict": r.verdict,
                "detail": det,
                "data_ts": r.data_ts.isoformat() if r.data_ts else None,
                # 🚨 Surfaced, not hidden: a call made on input hours older than
                # the observation is a call made on stale data, and the reader
                # deserves to see that next to the outcome.
                "data_age_min": (
                    round((r.call_ts - r.data_ts).total_seconds() / 60.0)
                    if (r.call_ts and r.data_ts) else None),
            })
        return out
    except Exception:
        return []
    finally:
        db.close()


def upsert_spy_days(bars: list[dict]) -> int:
    """Store SPY daily bars. `bars` are Tradier /markets/history day dicts."""
    if SessionLocal is None or not bars:
        return 0
    db = SessionLocal()
    n = 0
    try:
        for b in bars:
            try:
                d = date.fromisoformat(str(b.get("date"))[:10])
            except Exception:
                continue
            row = db.get(SpyDaily, d)
            if row is None:
                row = SpyDaily(trade_date=d)
                db.add(row)
            for k in ("open", "high", "low", "close"):
                v = b.get(k)
                if v is not None:
                    try:
                        setattr(row, k, float(v))
                    except (TypeError, ValueError):
                        pass
            n += 1
        db.commit()
        return n
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[call_log] spy upsert failed ({type(e).__name__})")
        return 0
    finally:
        db.close()


def spy_frame(days: int = 400, now: Optional[datetime] = None) -> dict[str, dict]:
    """{iso_date: {open, close, prev_close, next_open}} for outcome joins."""
    if SessionLocal is None:
        return {}
    ts = now or _now_ct()
    since = ts.date() - timedelta(days=max(2, int(days)) + 10)
    db = SessionLocal()
    try:
        rows = (db.query(SpyDaily)
                  .filter(SpyDaily.trade_date >= since)
                  .order_by(SpyDaily.trade_date).all())
    except Exception:
        return {}
    finally:
        db.close()

    out: dict[str, dict] = {}
    for i, r in enumerate(rows):
        prev_close = rows[i - 1].close if i > 0 else None
        # 🚨 The NEXT SESSION's open, not "tomorrow's" - a Friday call is scored
        # against Monday. Walking the row list gives that for free; calendar
        # arithmetic would silently score Friday against a market holiday.
        nxt_open = rows[i + 1].open if i + 1 < len(rows) else None
        out[r.trade_date.isoformat()] = {
            "open": r.open, "close": r.close,
            "prev_close": prev_close, "next_open": nxt_open,
        }
    return out
