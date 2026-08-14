"""Risk Advisor — read-only advisory endpoints. ADVISORY ONLY: no bot reads this.

Signal stack (validated 2026-08-12, ironforge-data/risk_advisor — every claim
pre-registered and backtested; see trials_registry.md there):

  DEPLOYABLE
    * backwardation skip     : VIX > VIX3M          (+0.09 ret/DD, 7 yrs)
    * VIX1D daily flag       : VIX1D/sqrt(252) > 1% (42.8% prec / 68% recall)
    * double_floor calm      : VVIX < 85 and VIX < 14 (0.00x next-day tail)
    * 10:00 CT flow spike    : put-vol z or total z > 2 vs trailing-63 baseline
                               (P(big rest-of-day move) 28.6% vs 12.1%, ~4.8 sigma)
    * 12:00/13:30 CT re-checks: FRESH put/total z > 2 at each clock vs its own
                               trailing-63 same-clock baseline (12:00: P(|move
                               to close| >= 0.5%) 29.3% vs 17.0% base, 1.73x;
                               13:30: 17.0% vs 8.4% base, 2.03x)
    * rolling flow watcher   : put/total z > 2 vs a per-minute trailing-63
                               baseline, polled every 10 min 10:36-14:00 CT
                               (registry #39: P(|move to close| >= 0.5%)
                               34.2% vs 22.4% minute-matched base, 1.53x,
                               4/4 years). Catches spikes the fixed clocks
                               miss; suppressed when a fixed clock already
                               alerted a spike that day (see risk_alerts.py).
  WATCH (accumulating evidence, NOT trading signals)
    * quiet-day 0DTE OTM call z (squeeze tell)  — right shape, underpowered
    * premium-imbalance contrarian              — suggestive only

Flow z-scores compare TODAY's cumulative volume at the 10:00 CT snapshot with
the SAME window over the trailing 63 sessions. The historical baseline ships as
a committed CSV (backend/data/risk_flow_baseline.csv, built from the local
research warehouse); live days extend it via lazily-captured snapshots.

The snapshot is captured lazily: the first /state request at/after 10:00 CT
each session pulls Tradier chain volumes once and persists them. Before the
snapshot exists, flow fields are null and `flow_status` says why.
"""
from __future__ import annotations

import asyncio
import csv
import json
import math
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Request
from sqlalchemy import Column, Date, DateTime, Float, BigInteger, String

from .db import Base, SessionLocal

router = APIRouter(prefix="/api/spreadworks/risk-advisor", tags=["Risk Advisor"])

CT = ZoneInfo("America/Chicago")
SQRT252 = 15.874507866387544
TRAIL = 63
OTM_BAND = 0.005
QUIET_VIX = 16.0
SNAPSHOT_CT = (10, 0)          # 10:00 CT — the validated clock
# Capture must happen NEAR the clock or the stored volumes are not the 10:00
# figure at all. The first deploy captured at 18:18 CT and stored end-of-day
# cumulative volume labeled as the 10:00 snapshot — vs a 10:00 baseline that
# reads as a huge false spike. Window enforced on WRITE and on READ, so any
# polluted row is neutralized without a migration.
SNAPSHOT_WINDOW_END_CT = (10, 35)
# Afternoon re-check clocks — same capture-window discipline as the 10:00
# snapshot, one CSV baseline shared by both clocks (filtered by the `clock`
# column). A late capture at either clock is not that clock's figure, so the
# window is enforced on write AND read exactly like SNAPSHOT_CT above.
PM_CLOCKS: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "12:00": ((12, 0), (12, 35)),
    "13:30": ((13, 30), (14, 5)),
}
# Rolling flow watcher (registry #39, validated 2026-08-13) — polls every 10
# minutes across the window the fixed 10:00/12:00/13:30 clocks do NOT read
# minute-by-minute, so it exists to catch spikes those clocks miss, not to
# duplicate them (suppression lives in risk_alerts.rolling_flow_check). The
# baseline is keyed by ET minute-of-day (571 = 09:31 ET); this window (696-
# 900) is 10:36-14:00 CT.
ROLLING_WINDOW_CT: tuple[tuple[int, int], tuple[int, int]] = ((10, 36), (14, 0))
ROLLING_BASELINE_JSON = Path(__file__).resolve().parent / "data" / "rolling_flow_baselines.json"
CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv"
BASELINE_CSV = Path(__file__).resolve().parent / "data" / "risk_flow_baseline.csv"
BASELINE_CSV_PM = Path(__file__).resolve().parent / "data" / "risk_flow_baseline_pm.csv"

_cboe_cache: dict[str, tuple[datetime, dict[date, float]]] = {}
_CBOE_TTL = 1800
_snapshot_lock = asyncio.Lock()


class RiskFlowSnapshot(Base):
    """One row per session: cumulative SPY option volume at the 10:00 CT clock."""
    __tablename__ = "risk_flow_snapshots"
    d = Column(Date, primary_key=True)
    captured_at = Column(DateTime)
    callv = Column(BigInteger)
    putv = Column(BigInteger)
    totv = Column(BigInteger)
    otm_call_0dte = Column(BigInteger)
    spot = Column(Float)


class RiskFlowSnapshotPM(Base):
    """One row per (session, clock): cumulative SPY option volume at the
    12:00 or 13:30 CT afternoon re-check clock."""
    __tablename__ = "risk_flow_snapshots_pm"
    d = Column(Date, primary_key=True)
    clock = Column(String(5), primary_key=True)
    captured_at = Column(DateTime)
    callv = Column(BigInteger)
    putv = Column(BigInteger)
    totv = Column(BigInteger)


class RiskFlowRollingState(Base):
    """Latest ROLLING flow-watcher reading (registry #39) — OVERWRITTEN on
    every successful 10-min poll across the 10:36-14:00 CT window, so
    /state can show the current z without re-hitting Tradier on every page
    load (the page refreshes every 60s). One row per session; unlike
    RiskFlowSnapshot/RiskFlowSnapshotPM this isn't a single validated clock
    — the whole window is the signal, so there's nothing to window-guard on
    read (risk_alerts only ever writes from inside the window)."""
    __tablename__ = "risk_flow_rolling_state"
    d = Column(Date, primary_key=True)
    captured_at = Column(DateTime)
    putv_z = Column(Float)
    totv_z = Column(Float)


class RiskHealthState(Base):
    """Last known health status per scorecard signal (flag_vix1d,
    calibration, flow_spike). Lets risk_alerts.health_flip_check() detect a
    status CHANGE day-to-day (sharp <-> DEGRADED) instead of re-announcing
    the same status every afternoon."""
    __tablename__ = "risk_health_state"
    signal = Column(String(30), primary_key=True)
    status = Column(String(20))
    updated_at = Column(DateTime)


def _norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


async def _cboe(client: httpx.AsyncClient, sym: str) -> dict[date, float]:
    now = datetime.utcnow()
    hit = _cboe_cache.get(sym)
    if hit and (now - hit[0]).total_seconds() < _CBOE_TTL:
        return hit[1]
    r = await client.get(CBOE_URL.format(sym=sym),
                         headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    out: dict[date, float] = {}
    lines = r.text.splitlines()
    for ln in lines[1:]:
        parts = ln.split(",")
        if len(parts) < 2:
            continue
        try:
            d = datetime.strptime(parts[0].strip(), "%m/%d/%Y").date()
            out[d] = float(parts[-1])
        except ValueError:
            continue
    _cboe_cache[sym] = (now, out)
    return out


def _latest(series: dict[date, float]) -> tuple[date, float]:
    d = max(series)
    return d, series[d]


def _baseline_rows() -> list[dict]:
    rows = []
    if not BASELINE_CSV.exists():
        # Committed seed missing — flow z-scores stay null rather than 500ing.
        return rows
    with open(BASELINE_CSV, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({"d": date.fromisoformat(r["d"]),
                         "callv": int(r["callv"]), "putv": int(r["putv"]),
                         "totv": int(r["totv"]),
                         "otm_call_0dte": int(r["otm_call_0dte"])})
    rows.sort(key=lambda r: r["d"])
    return rows


def _flow_history() -> list[dict]:
    """Committed baseline + any live snapshots, deduped, sorted."""
    rows = {r["d"]: r for r in _baseline_rows()}
    if SessionLocal is not None:
        try:
            db = SessionLocal()
            for r in db.query(RiskFlowSnapshot).all():
                if not _snap_valid(r.captured_at):
                    continue        # late captures are not 10:00 figures
                rows[r.d] = {"d": r.d, "callv": r.callv, "putv": r.putv,
                             "totv": r.totv, "otm_call_0dte": r.otm_call_0dte}
            db.close()
        except Exception:
            pass
    return [rows[k] for k in sorted(rows)]


def _pm_baseline_rows(clock: str) -> list[dict]:
    rows = []
    if not BASELINE_CSV_PM.exists():
        # Committed seed missing — PM flow z-scores stay null rather than 500ing.
        return rows
    with open(BASELINE_CSV_PM, newline="") as f:
        for r in csv.DictReader(f):
            if r["clock"] != clock:
                continue
            rows.append({"d": date.fromisoformat(r["d"]),
                         "callv": int(r["callv"]), "putv": int(r["putv"]),
                         "totv": int(r["totv"])})
    rows.sort(key=lambda r: r["d"])
    return rows


def _pm_flow_history(clock: str) -> list[dict]:
    """Committed PM baseline for this clock + any live snapshots, deduped,
    sorted — mirrors _flow_history()."""
    rows = {r["d"]: r for r in _pm_baseline_rows(clock)}
    if SessionLocal is not None:
        try:
            db = SessionLocal()
            q = db.query(RiskFlowSnapshotPM).filter(RiskFlowSnapshotPM.clock == clock)
            for r in q.all():
                if not _pm_snap_valid(clock, r.captured_at):
                    continue        # late captures are not this clock's figure
                rows[r.d] = {"d": r.d, "callv": r.callv, "putv": r.putv,
                             "totv": r.totv}
            db.close()
        except Exception:
            pass
    return [rows[k] for k in sorted(rows)]


def _z(cur: float, hist: list[float]) -> float | None:
    h = hist[-TRAIL:]
    if len(h) < 40:
        return None
    m = sum(h) / len(h)
    var = sum((x - m) ** 2 for x in h) / (len(h) - 1)
    if var <= 0:
        return None
    return (cur - m) / math.sqrt(var)


_rolling_baseline_cache: dict[int, dict] | None = None


def _rolling_baseline() -> dict[int, dict]:
    """Load+cache the per-ET-minute trailing-63 baseline (backend/data/
    rolling_flow_baselines.json — precomputed mean/sd of CUMULATIVE session
    put/total volume, one row per minute). Missing file -> empty dict, so
    the rolling z-scores stay null rather than 500ing (mirrors
    _baseline_rows())."""
    global _rolling_baseline_cache
    if _rolling_baseline_cache is not None:
        return _rolling_baseline_cache
    out: dict[int, dict] = {}
    if ROLLING_BASELINE_JSON.exists():
        with open(ROLLING_BASELINE_JSON) as f:
            data = json.load(f)
        out = {int(k): v for k, v in (data.get("baselines") or {}).items()}
    _rolling_baseline_cache = out
    return out


def _ct_to_et_minute(hm: tuple[int, int]) -> int:
    """CT (hour, minute) -> ET minute-of-day. ET is exactly 60 minutes ahead
    of CT year-round (both shift for DST together) — matches the baseline
    file's convention (571 = 09:31 ET)."""
    h, m = hm
    return h * 60 + m + 60


def _rolling_baseline_at(now_ct: datetime) -> dict | None:
    """The baseline row for the nearest ET minute AT-OR-BEFORE now — grading
    today's cumulative volume against a LATER minute's (higher) baseline
    would understate how unusual the current reading actually is."""
    baseline = _rolling_baseline()
    if not baseline:
        return None
    et_minute = _ct_to_et_minute((now_ct.hour, now_ct.minute))
    candidates = [k for k in baseline if k <= et_minute]
    if not candidates:
        return None
    return baseline[max(candidates)]


def _rolling_z(cur: float, mean: float, sd: float) -> float | None:
    if not sd or sd <= 0:
        return None
    return (cur - mean) / sd


async def _rolling_flow_now(request: Request) -> dict | None:
    """Current cumulative SPY put/total option volume — the SAME Tradier
    chain-volume source the 10:00/12:00/13:30 clocks read, fetched fresh on
    every call (no once-per-day capture gate) since the rolling watcher
    polls every 10 minutes through its whole window."""
    try:
        from .routes import _tradier_get, _get_quote  # existing helpers
        today = datetime.now(CT).date()
        q = await _get_quote(request, "SPY")
        spot = float(q.get("last") or q.get("close") or 0)
        if spot <= 0:
            return None
        exps = await _tradier_get(request, "/markets/options/expirations",
                                  {"symbol": "SPY"})
        all_exps = (exps.get("expirations") or {}).get("date") or []
        if isinstance(all_exps, str):
            all_exps = [all_exps]
        near = [e for e in all_exps if e <= (today + timedelta(days=7)).isoformat()][:5]
        callv = putv = 0
        for exp in near:
            ch = await _tradier_get(request, "/markets/options/chains",
                                    {"symbol": "SPY", "expiration": exp})
            opts = (ch.get("options") or {}).get("option") or []
            if isinstance(opts, dict):
                opts = [opts]
            for o in opts:
                v = int(o.get("volume") or 0)
                if not v:
                    continue
                if o.get("option_type") == "call":
                    callv += v
                else:
                    putv += v
        return {"putv": putv, "totv": callv + putv, "spot": spot}
    except Exception:
        return None


def _save_rolling_state(d: date, captured_at: datetime, pz: float | None,
                        tz: float | None) -> None:
    """Overwrite today's rolling-watcher reading. Called on EVERY successful
    poll (not just ones that cross the alert threshold) so /state always
    shows the current z without hitting Tradier itself."""
    if SessionLocal is None:
        return
    db = SessionLocal()
    try:
        row = db.get(RiskFlowRollingState, d)
        if row is None:
            row = RiskFlowRollingState(d=d)
            db.add(row)
        row.captured_at = captured_at
        row.putv_z = pz
        row.totv_z = tz
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _rolling_fired_today(d: date) -> bool:
    """Read-only: did the rolling watcher already post its once-per-day
    alert today? Mirrors risk_alerts._already_posted() without importing
    that module (risk_alerts imports FROM here)."""
    if SessionLocal is None:
        return False
    try:
        from .models import DiscordPostLog
        db = SessionLocal()
        try:
            return db.get(DiscordPostLog, ("risk_flow_rolling", d)) is not None
        finally:
            db.close()
    except Exception:
        return False


def _snap_valid(captured_at: datetime) -> bool:
    """A snapshot is only the 10:00 figure if captured inside the window.

    captured_at is stored CT-naive going forward. Rows written before the
    2026-08-12 fix round-tripped as naive UTC; none of those fall in the CT
    window (the one legacy row is 23:18), so a plain CT check is also correct
    for legacy data."""
    t = (captured_at.hour, captured_at.minute)
    return SNAPSHOT_CT <= t <= SNAPSHOT_WINDOW_END_CT


def _snap_dict(row: RiskFlowSnapshot) -> dict:
    return {"d": row.d, "captured_at": row.captured_at, "callv": row.callv,
            "putv": row.putv, "totv": row.totv,
            "otm_call_0dte": row.otm_call_0dte, "spot": row.spot}


def _pm_snap_valid(clock: str, captured_at: datetime) -> bool:
    """A PM snapshot is only that clock's figure if captured inside its
    window — same reasoning as _snap_valid() for the 10:00 clock."""
    start, end = PM_CLOCKS[clock]
    t = (captured_at.hour, captured_at.minute)
    return start <= t <= end


def _pm_snap_dict(row: RiskFlowSnapshotPM) -> dict:
    return {"d": row.d, "clock": row.clock, "captured_at": row.captured_at,
            "callv": row.callv, "putv": row.putv, "totv": row.totv}


async def _capture_snapshot(request: Request) -> dict | None:
    """Lazily capture today's 10:00 CT flow snapshot from Tradier (once).

    Returns a PLAIN DICT — never a live ORM instance. The first deploy
    returned the instance after closing its session and every attribute read
    raised DetachedInstanceError.
    """
    if SessionLocal is None:
        return None
    today = datetime.now(CT).date()
    db = SessionLocal()
    try:
        row = db.get(RiskFlowSnapshot, today)
        if row:
            return _snap_dict(row) if _snap_valid(row.captured_at) else None
        now_ct = datetime.now(CT)
        t = (now_ct.hour, now_ct.minute)
        if t < SNAPSHOT_CT or t > SNAPSHOT_WINDOW_END_CT or now_ct.weekday() >= 5:
            return None
        async with _snapshot_lock:
            row = db.get(RiskFlowSnapshot, today)
            if row:
                return _snap_dict(row) if _snap_valid(row.captured_at) else None
            from .routes import _tradier_get, _get_quote  # existing helpers
            q = await _get_quote(request, "SPY")
            spot = float(q.get("last") or q.get("close") or 0)
            if spot <= 0:
                return None
            exps = await _tradier_get(request, "/markets/options/expirations",
                                      {"symbol": "SPY"})
            all_exps = (exps.get("expirations") or {}).get("date") or []
            if isinstance(all_exps, str):
                all_exps = [all_exps]
            near = [e for e in all_exps if e <= (today + timedelta(days=7)).isoformat()][:5]
            callv = putv = otm0 = 0
            for exp in near:
                ch = await _tradier_get(request, "/markets/options/chains",
                                        {"symbol": "SPY", "expiration": exp})
                opts = (ch.get("options") or {}).get("option") or []
                if isinstance(opts, dict):
                    opts = [opts]
                for o in opts:
                    v = int(o.get("volume") or 0)
                    if not v:
                        continue
                    if o.get("option_type") == "call":
                        callv += v
                        if exp == today.isoformat() and \
                                float(o.get("strike", 0)) > spot * (1 + OTM_BAND):
                            otm0 += v
                    else:
                        putv += v
            # Store CT-NAIVE. An aware datetime round-trips through Postgres
            # as naive UTC (observed: an 18:18 CT capture read back as 23:18),
            # which would make the CT-window check reject every legitimate
            # capture too. Naive-CT in, naive-CT out.
            row = RiskFlowSnapshot(d=today,
                                   captured_at=datetime.now(CT).replace(tzinfo=None),
                                   callv=callv, putv=putv, totv=callv + putv,
                                   otm_call_0dte=otm0, spot=spot)
            db.add(row)
            db.commit()
            return {"d": today, "captured_at": row.captured_at,
                    "callv": callv, "putv": putv, "totv": callv + putv,
                    "otm_call_0dte": otm0, "spot": spot}
    except Exception:
        return None
    finally:
        db.close()


async def _capture_pm_snapshot(request: Request, clock: str) -> dict | None:
    """Lazily capture today's afternoon re-check snapshot (12:00 or 13:30 CT),
    once per (day, clock). Mirrors _capture_snapshot(): Tradier's `volume`
    field is already the cumulative day total at fetch time, so pulling it
    inside the clock's window IS the open->clock cumulative — same semantics
    the baseline CSV was built with.

    Returns a PLAIN DICT — never a live ORM instance (see _capture_snapshot
    docstring for why).
    """
    if SessionLocal is None or clock not in PM_CLOCKS:
        return None
    today = datetime.now(CT).date()
    db = SessionLocal()
    try:
        row = db.get(RiskFlowSnapshotPM, (today, clock))
        if row:
            return _pm_snap_dict(row) if _pm_snap_valid(clock, row.captured_at) else None
        now_ct = datetime.now(CT)
        t = (now_ct.hour, now_ct.minute)
        start, end = PM_CLOCKS[clock]
        if t < start or t > end or now_ct.weekday() >= 5:
            return None
        async with _snapshot_lock:
            row = db.get(RiskFlowSnapshotPM, (today, clock))
            if row:
                return _pm_snap_dict(row) if _pm_snap_valid(clock, row.captured_at) else None
            from .routes import _tradier_get, _get_quote  # existing helpers
            q = await _get_quote(request, "SPY")
            spot = float(q.get("last") or q.get("close") or 0)
            if spot <= 0:
                return None
            exps = await _tradier_get(request, "/markets/options/expirations",
                                      {"symbol": "SPY"})
            all_exps = (exps.get("expirations") or {}).get("date") or []
            if isinstance(all_exps, str):
                all_exps = [all_exps]
            near = [e for e in all_exps if e <= (today + timedelta(days=7)).isoformat()][:5]
            callv = putv = 0
            for exp in near:
                ch = await _tradier_get(request, "/markets/options/chains",
                                        {"symbol": "SPY", "expiration": exp})
                opts = (ch.get("options") or {}).get("option") or []
                if isinstance(opts, dict):
                    opts = [opts]
                for o in opts:
                    v = int(o.get("volume") or 0)
                    if not v:
                        continue
                    if o.get("option_type") == "call":
                        callv += v
                    else:
                        putv += v
            row = RiskFlowSnapshotPM(d=today, clock=clock,
                                     captured_at=datetime.now(CT).replace(tzinfo=None),
                                     callv=callv, putv=putv, totv=callv + putv)
            db.add(row)
            db.commit()
            return {"d": today, "clock": clock, "captured_at": row.captured_at,
                    "callv": callv, "putv": putv, "totv": callv + putv}
    except Exception:
        return None
    finally:
        db.close()


_live_cache: dict = {}
_LIVE_TTL = 60
_intraday_cache: dict = {}
_INTRADAY_TTL = 60
_spyhist_cache: dict = {}
_SPYHIST_TTL = 1800
_recipe_cache: dict = {}
_RECIPE_TTL = 60

# ── Layer separation (Corrective Brief v2 §7) ────────────────────────────────
# The risk model outputs probability/magnitude/confidence. The ONLY actions any
# endpoint may emit are this whitelist. It must never name an instrument or a
# structure. Enforced at runtime by _scrub() on every response and in CI by
# tests/test_risk_whitelist.py — not by convention.
ACTION_WHITELIST = frozenset({
    "normal", "reduce_size", "widen_or_skip", "skip_entry",
    "close_early", "stand_down",
})
# Structures/terms the payload may never contain (v2 §7.2). Checked
# case-insensitively as substrings of every string in every response.
PROHIBITED_TERMS = (
    "straddle", "strangle", "calendar spread", "diagonal", "ratio spread",
    "back spread", "backspread", "vix call", "buy premium", "buy volatility",
    "long call", "long put", "debit spread", "buy calls", "buy puts",
)
# v2 §11.3 ladder, frozen. 0.55-0.75 is widen-strikes-or-skip — "hedge" was a
# whitelist violation and is retired.
GRADES = [(0.75, "stand_down"), (0.55, "widen_or_skip"), (0.35, "reduce_size")]


def _scrub(obj):
    """Recursively strip prohibited structure terms from a response payload.

    Defense in depth: nothing in this module emits these terms, but if any
    future edit does, the payload self-redacts instead of shipping a
    structure recommendation."""
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    if isinstance(obj, str):
        low = obj.lower()
        if any(t in low for t in PROHIBITED_TERMS):
            return "[blocked: structure terms are prohibited on this endpoint]"
    return obj


async def _live_quote(request: Request) -> dict | None:
    """SPY last + prev close, cached 60s. Never raises."""
    now = datetime.now(CT)
    hit = _live_cache.get("q")
    if hit and (now - hit[0]).total_seconds() < _LIVE_TTL:
        return hit[1]
    try:
        from .routes import _get_quote
        q = await _get_quote(request, "SPY")
        out = {"last": float(q.get("last") or 0),
               "prev_close": float(q.get("prevclose") or q.get("prev_close") or 0)}
        if out["last"] > 0 and out["prev_close"] > 0:
            out["chg_pct"] = (out["last"] / out["prev_close"] - 1.0) * 100.0
            _live_cache["q"] = (now, out)
            return out
    except Exception:
        pass
    return hit[1] if hit else None


async def _spy_daily_rets(request: Request) -> list[float]:
    """Trailing daily % returns from Tradier history, cached 30 min."""
    now = datetime.now(CT)
    hit = _spyhist_cache.get("r")
    if hit and (now - hit[0]).total_seconds() < _SPYHIST_TTL:
        return hit[1]
    try:
        from .routes import _tradier_get
        start = (now.date() - timedelta(days=560)).isoformat()
        h = await _tradier_get(request, "/markets/history",
                               {"symbol": "SPY", "interval": "daily",
                                "start": start, "end": now.date().isoformat()})
        days = ((h.get("history") or {}).get("day")) or []
        closes = [(d["date"], float(d["close"])) for d in days if d.get("close")]
        closes.sort()
        rets = [(closes[i][0],
                 (closes[i][1] / closes[i - 1][1] - 1.0) * 100.0)
                for i in range(1, len(closes))]
        _spyhist_cache["r"] = (now, rets)
        return rets
    except Exception:
        return hit[1] if hit else []


def _outlook(vix_c, v9_c, v1_hist: dict, rets: list) -> dict | None:
    """Next-session probabilities from latest closes — the same construction
    as the validated shadow publisher (raw for ranking, Albers-style 252d
    RVRP adjustment for calibrated probability values)."""
    if not v1_hist or not rets:
        return None
    d1, v1_c = _latest(v1_hist)
    # 252d mean of daily RVRP ratios: sqrt(pi/2)*|ret| / (VIX1D/sqrt252)
    rmap = dict(rets)
    ratios = []
    for d, v in sorted(v1_hist.items()):
        r = rmap.get(d.isoformat())
        if r is not None and v:
            ratios.append(math.sqrt(math.pi / 2.0) * abs(r) / (v / SQRT252))
    if len(ratios) < 100:
        return None
    rvrp = sum(ratios[-252:]) / len(ratios[-252:])
    sig_raw = v1_c / SQRT252
    sig_adj = sig_raw * rvrp
    return {
        "asof_close": d1.isoformat(),
        "vix1d": v1_c,
        "p_big_raw": 2 * _norm_cdf(-1.0 / sig_raw),
        "p_big_adj": 2 * _norm_cdf(-1.0 / sig_adj),
        "p_down_adj": _norm_cdf(-1.0 / sig_adj),
        "p_down2s": _norm_cdf(-2.0 * vix_c / v9_c) if v9_c else None,
        "flag_vix1d": sig_raw > 1.0,
        "grade": next((g for thr, g in GRADES
                       if 2 * _norm_cdf(-1.0 / sig_adj) >= thr), "normal"),
        "implied_move_pct": sig_raw,
    }



def _macro_block() -> dict:
    """Factual macro-calendar context (sourced; see econ_calendar.py)."""
    try:
        from .econ_calendar import macro_today, next_macro
        today = datetime.now(CT).date()
        return {"today": macro_today(today), "next": next_macro(today)}
    except Exception:
        return {"today": None, "next": None}


# ── /recipe: the one manual ticket that survived 44 registered trials ───────
# Registry #23b (AM, 10:05-10:20 CT) + #41 (PM, 13:05-13:10 CT) — a same-day
# SPY vertical, short strike spot-2, wing 5 wide. EBB/EBB-PM run exactly this
# spec on paper (see bots/registry.py); this endpoint is the read-only manual
# companion for a human placing the same ticket by hand — it never trades.


def _recipe_strikes(spot: float) -> tuple[int, int]:
    """Short strike = spot rounded down/up to the nearest $1 minus 2; the
    other leg sits 5 points further out (SPY $1 grid) — the exact registry
    #23b/#41 spec, kept as a pure function so the strike math is unit
    testable without a live quote or a Tradier round-trip."""
    short_strike = round(spot - 2)
    other_strike = short_strike - 5
    return short_strike, other_strike


def _recipe_windows() -> tuple[tuple[int, int], tuple[int, int],
                               tuple[int, int], tuple[int, int]]:
    """AM/PM entry windows read straight from the ebb/ebb_pm registry
    defaults — the registry is the single source of truth for these clocks,
    this endpoint must never hardcode a copy that can drift from it."""
    from .bots.registry import BOT_REGISTRY

    def _hm(s: str) -> tuple[int, int]:
        h, m = s.split(":")
        return int(h), int(m)

    am = BOT_REGISTRY["ebb"]["defaults"]
    pm = BOT_REGISTRY["ebb_pm"]["defaults"]
    return (_hm(am["entry_start_ct"]), _hm(am["entry_end_ct"]),
            _hm(pm["entry_start_ct"]), _hm(pm["entry_end_ct"]))


def _recipe_phase(now_ct: datetime, am_start: tuple[int, int],
                  am_end: tuple[int, int], pm_start: tuple[int, int],
                  pm_end: tuple[int, int]) -> tuple[str, int | None]:
    """Phase + minutes-to-next-window from (hour, minute) tuples — mirrors
    the (hour, minute) comparisons _snap_valid/_pm_snap_valid already use
    elsewhere in this module rather than inventing a new time convention."""
    if now_ct.weekday() >= 5:
        return "weekend", None
    total = now_ct.hour * 60 + now_ct.minute
    am_s, am_e = am_start[0] * 60 + am_start[1], am_end[0] * 60 + am_end[1]
    pm_s, pm_e = pm_start[0] * 60 + pm_start[1], pm_end[0] * 60 + pm_end[1]
    if total < am_s:
        return "before_am", am_s - total
    if am_s <= total <= am_e:
        return "am_open", None
    if am_e < total < pm_s:
        return "between", pm_s - total
    if pm_s <= total <= pm_e:
        return "pm_open", None
    return "done", None


@router.get("/recipe")
async def recipe(request: Request):
    """Today's manual ticket, cached 60s. Never raises — any failure
    degrades to {"status": "unavailable"} rather than a 500, same discipline
    as every other endpoint in this module."""
    now = datetime.now(CT)
    hit = _recipe_cache.get("r")
    if hit and (now - hit[0]).total_seconds() < _RECIPE_TTL:
        return hit[1]
    try:
        am_start, am_end, pm_start, pm_end = _recipe_windows()
        phase, minutes_to_next = _recipe_phase(now, am_start, am_end, pm_start, pm_end)

        live = await _live_quote(request)
        spot = (live.get("last") or live.get("prev_close")) if live else None
        if not spot:
            payload = _scrub({"status": "no quote", "generated_at": now.isoformat()})
            _recipe_cache["r"] = (now, payload)
            return payload

        short_strike, other_strike = _recipe_strikes(spot)
        today = now.date()

        # Fetch a live estimate only near either clock — everywhere else
        # this would just be extra Tradier load for a number nobody can act
        # on yet.
        total = now.hour * 60 + now.minute
        am_s, am_e = am_start[0] * 60 + am_start[1], am_end[0] * 60 + am_end[1]
        pm_s, pm_e = pm_start[0] * 60 + pm_start[1], pm_end[0] * 60 + pm_end[1]
        near_window = (am_s - 20 <= total <= am_e) or (pm_s - 20 <= total <= pm_e)

        credit_now = None
        meets_floor = None
        if near_window and now.weekday() < 5:
            try:
                from .routes import _tradier_get
                ch = await _tradier_get(request, "/markets/options/chains",
                                        {"symbol": "SPY", "expiration": today.isoformat()})
                opts = (ch.get("options") or {}).get("option") or []
                if isinstance(opts, dict):
                    opts = [opts]
                puts = {float(o["strike"]): o for o in opts
                        if o.get("option_type") == "put" and o.get("strike") is not None}
                near_opt = puts.get(float(short_strike))
                far_opt = puts.get(float(other_strike))
                if near_opt and far_opt:
                    near_bid = float(near_opt.get("bid") or 0)
                    far_ask = float(far_opt.get("ask") or 0)
                    if near_bid > 0 and far_ask > 0:
                        credit_now = round(near_bid - far_ask, 2)
                        meets_floor = credit_now >= 0.10
            except Exception:
                credit_now = None
                meets_floor = None

        payload = _scrub({
            "status": "ok",
            "spot": spot,
            "expiration": today.isoformat(),
            "short_strike": short_strike,
            "long_strike": other_strike,
            "phase": phase,
            "minutes_to_next_window": minutes_to_next,
            "credit_now": credit_now,
            "meets_floor": meets_floor,
            "floor": 0.10,
            "generated_at": now.isoformat(),
        })
        _recipe_cache["r"] = (now, payload)
        return payload
    except Exception:
        return {"status": "unavailable"}


@router.get("/state")
async def state(request: Request):
    client: httpx.AsyncClient = request.app.state.http
    vix = await _cboe(client, "VIX")
    v3 = await _cboe(client, "VIX3M")
    v9 = await _cboe(client, "VIX9D")
    v1 = await _cboe(client, "VIX1D")
    vvix = await _cboe(client, "VVIX")

    d_vix, vix_c = _latest(vix)
    v3_c = v3.get(d_vix)
    v9_c = v9.get(d_vix)
    v1_c = v1.get(d_vix)
    vv_c = vvix.get(d_vix)

    flag_vix1d = bool(v1_c and v1_c / SQRT252 > 1.0)
    backwardation = bool(v3_c and vix_c > v3_c)
    inv_9d = bool(v9_c and v9_c > vix_c)
    double_floor = bool(vv_c and vv_c < 85 and vix_c < 14)
    quiet = vix_c < QUIET_VIX
    p_down2s = _norm_cdf(-2.0 * vix_c / v9_c) if v9_c else None

    # today's flow snapshot (lazy capture at/after 10:00 CT)
    snap = await _capture_snapshot(request)
    hist = _flow_history()
    today = datetime.now(CT).date()
    prior = [r for r in hist if r["d"] < today]
    now_ct = datetime.now(CT)
    if snap is None:
        if now_ct.weekday() >= 5:
            st = "weekend — no capture"
        elif (now_ct.hour, now_ct.minute) < SNAPSHOT_CT:
            st = "pre-window — captures at first request 10:00–10:35 CT"
        else:
            st = "no valid snapshot today (capture window 10:00–10:35 CT missed)"
    else:
        st = "snapshot"
    flow = {"status": st, "putv_z": None, "totv_z": None,
            "otm_call_0dte_z": None, "spike": None}
    if snap is not None:
        pz = _z(snap["putv"], [r["putv"] for r in prior])
        tz = _z(snap["totv"], [r["totv"] for r in prior])
        oz = _z(snap["otm_call_0dte"], [r["otm_call_0dte"] for r in prior])
        flow.update({"captured_at": snap["captured_at"].isoformat(),
                     "putv_z": pz, "totv_z": tz, "otm_call_0dte_z": oz,
                     "spike": bool((pz or 0) > 2 or (tz or 0) > 2)})

    # afternoon re-check clocks (12:00 / 13:30 CT) — same lazy-capture,
    # window-enforced pattern as the 10:00 snapshot, graded against their own
    # trailing-63 same-clock history.
    flow_pm: dict = {}
    for clock, (start, end) in PM_CLOCKS.items():
        snap_pm = await _capture_pm_snapshot(request, clock)
        hist_pm = _pm_flow_history(clock)
        prior_pm = [r for r in hist_pm if r["d"] < today]
        window = f"{start[0]:02d}:{start[1]:02d}–{end[0]:02d}:{end[1]:02d} CT"
        if snap_pm is None:
            if now_ct.weekday() >= 5:
                st_pm = "weekend — no capture"
            elif (now_ct.hour, now_ct.minute) < start:
                st_pm = f"pre-window — captures at first request {window}"
            else:
                st_pm = f"no valid snapshot today (capture window {window} missed)"
        else:
            st_pm = "snapshot"
        entry = {"status": st_pm, "putv_z": None, "totv_z": None, "spike": None}
        if snap_pm is not None:
            pz_pm = _z(snap_pm["putv"], [r["putv"] for r in prior_pm])
            tz_pm = _z(snap_pm["totv"], [r["totv"] for r in prior_pm])
            entry.update({"captured_at": snap_pm["captured_at"].isoformat(),
                         "putv_z": pz_pm, "totv_z": tz_pm,
                         "spike": bool((pz_pm or 0) > 2 or (tz_pm or 0) > 2)})
        flow_pm[clock] = entry

    # rolling flow watcher (registry #39) — READ-ONLY here; the only writer
    # is risk_alerts.rolling_flow_check(), polling every 10 min through
    # 10:36-14:00 CT. This endpoint just surfaces the latest saved reading.
    flow_rolling: dict = {"putv_z": None, "totv_z": None, "captured_at": None,
                          "fired_today": False}
    if SessionLocal is not None:
        try:
            db = SessionLocal()
            row = db.get(RiskFlowRollingState, today)
            db.close()
            if row is not None:
                flow_rolling.update({
                    "putv_z": row.putv_z, "totv_z": row.totv_z,
                    "captured_at": row.captured_at.isoformat() if row.captured_at else None,
                })
        except Exception:
            pass
    flow_rolling["fired_today"] = _rolling_fired_today(today)

    live = await _live_quote(request)
    if live and v1_c:
        implied = v1_c / SQRT252
        live["expected_move_pct"] = implied
        live["move_budget_used"] = abs(live.get("chg_pct", 0)) / implied if implied else None
    rets = await _spy_daily_rets(request)
    outlook = _outlook(vix_c, v9_c, v1, rets)

    risk_off = backwardation or flag_vix1d or bool(flow["spike"])
    # explicit whitelist action (v2 §7.1): the ONLY instruction this endpoint
    # gives. "normal" on calm/no-signal days — the advisor never says "sell
    # more"; sizing up is not risk management.
    action = ("stand_down" if (backwardation and flag_vix1d) else
              "skip_entry" if risk_off else "normal")
    assert action in ACTION_WHITELIST
    return _scrub({
        "asof_close": d_vix.isoformat(),
        "generated_at": datetime.now(CT).isoformat(),
        "indices": {"vix": vix_c, "vix3m": v3_c, "vix9d": v9_c,
                    "vix1d": v1_c, "vvix": vv_c},
        "signals": {
            "backwardation": backwardation,
            "flag_vix1d": flag_vix1d,
            "inv_9d": inv_9d,
            "double_floor": double_floor,
            "quiet_vix": quiet,
            "p_down2s_ratio": p_down2s,
        },
        "flow": flow,
        "flow_pm": flow_pm,
        "flow_rolling": flow_rolling,
        "live": live,
        "outlook": outlook,
        "action": action,
        "macro": _macro_block(),
        "headline": ("RISK-OFF: stand down / reduce" if risk_off else
                     ("CALM FLOOR: safest premium-selling state" if double_floor
                      else "NORMAL")),
        "advisory_only": True,
    })


@router.get("/history")
async def history(request: Request, days: int = 90):
    client: httpx.AsyncClient = request.app.state.http
    vix = await _cboe(client, "VIX")
    hist = _flow_history()
    out = []
    for i, r in enumerate(hist):
        if i < TRAIL:
            continue
        prior = hist[max(0, i - TRAIL):i]
        vp = vix.get(r["d"] - timedelta(days=1)) or vix.get(r["d"] - timedelta(days=3))
        out.append({
            "d": r["d"].isoformat(),
            "putv_z": _z(r["putv"], [p["putv"] for p in prior]),
            "totv_z": _z(r["totv"], [p["totv"] for p in prior]),
            "otm_call_0dte_z": _z(r["otm_call_0dte"],
                                  [p["otm_call_0dte"] for p in prior]),
            "quiet": bool(vp and vp < QUIET_VIX) if vp else None,
        })
    return _scrub({"days": out[-days:]})


@router.get("/intraday")
async def intraday(request: Request):
    """Today's SPY 5-minute bars vs the VIX1D-implied expected move, cached 60s."""
    now = datetime.now(CT)
    hit = _intraday_cache.get("v")
    if hit and (now - hit[0]).total_seconds() < _INTRADAY_TTL:
        return hit[1]
    try:
        from .routes import _tradier_get
        today_iso = now.date().isoformat()
        h = await _tradier_get(request, "/markets/timesales",
                               {"symbol": "SPY", "interval": "5min",
                                "start": f"{today_iso} 08:30", "end": f"{today_iso} 15:05",
                                "session_filter": "open"})
        series = h.get("series")
        if not series or series == "null":
            payload = {"bars": [], "prev_close": None, "band_pct": None,
                       "snapshot_t": "10:00", "status": "no intraday bars yet",
                       "generated_at": now.isoformat()}
            _intraday_cache["v"] = (now, payload)
            return payload
        data = series.get("data") or []
        if isinstance(data, dict):
            data = [data]

        live = await _live_quote(request)
        prev_close = live.get("prev_close") if live else None

        client: httpx.AsyncClient = request.app.state.http
        band_pct = None
        try:
            v1 = await _cboe(client, "VIX1D")
            _, v1_c = _latest(v1)
            band_pct = v1_c / SQRT252
        except Exception:
            band_pct = None

        bars = []
        for b in data:
            t = b.get("time")
            close = b.get("close")
            if not t or close is None:
                continue
            dt_ct = datetime.fromisoformat(t).replace(
                tzinfo=ZoneInfo("America/New_York")).astimezone(CT)
            chg_pct = ((float(close) / prev_close - 1) * 100.0
                       if prev_close else None)
            bars.append({"t": dt_ct.strftime("%H:%M"), "price": float(close),
                        "chg_pct": chg_pct})

        payload = _scrub({"bars": bars, "prev_close": prev_close, "band_pct": band_pct,
                   "snapshot_t": "10:00", "status": "ok",
                   "generated_at": now.isoformat()})
        _intraday_cache["v"] = (now, payload)
        return payload
    except Exception:
        return {"bars": [], "status": "intraday unavailable"}


@router.get("/alert-log")
async def alert_log(limit: int = 30):
    """The channel and the page tell one story: last alerts actually posted
    (from the cross-replica dedupe log), newest first. Read-only."""
    FRIENDLY = {
        "risk_morning_riskoff": "RISK-OFF morning verdict (@here)",
        "risk_morning_calm": "Calm-floor note",
        "risk_em_note": "Expected-move note",
        "risk_em_breach": "EXPECTED-MOVE BREACH (@here)",
        "risk_flow_spike": "10:00 flow spike (@here)",
        "risk_pm_1200": "12:00 re-check spike (@here)",
        "risk_pm_1330": "13:30 re-check spike (@here)",
        "risk_flow_rolling": "Rolling flow spike (@here)",
        "risk_pm_fade_1200": "12:00 all-clear (spike faded)",
        "risk_pm_fade_1330": "13:30 all-clear (spike faded)",
        "risk_friday_digest": "Friday week-in-review",
    }
    rows = []
    if SessionLocal is not None:
        try:
            from .models import DiscordPostLog
            db = SessionLocal()
            q = (db.query(DiscordPostLog)
                   .filter(DiscordPostLog.message_key.like("risk_%"))
                   .order_by(DiscordPostLog.fire_date.desc(),
                             DiscordPostLog.message_key)
                   .limit(max(1, min(limit, 100))).all())
            rows = [{"d": r.fire_date.isoformat(),
                     "what": FRIENDLY.get(r.message_key, r.message_key)}
                    for r in q]
            db.close()
        except Exception:
            rows = []
    return _scrub({"alerts": rows})


@router.get("/scorecard")
async def scorecard(request: Request, days: int = 120):
    """Self-grading: what the advisory SAID each session vs what HAPPENED,
    scored against the backtest expectation bands. The page shows this so the
    tool's live track record is always visible next to its claims.

    Backtest bands being graded against:
      flag_vix1d  : 42.8% precision / 68.0% recall on |ret|>=1% days
      flow spike  : big-rest-of-day-move rate 28.6% vs 12.1% base
      p_big_adj   : Brier ~0.168 (calibrated arm)
    """
    client: httpx.AsyncClient = request.app.state.http
    vix = await _cboe(client, "VIX")
    v3 = await _cboe(client, "VIX3M")
    v1 = await _cboe(client, "VIX1D")
    rets = await _spy_daily_rets(request)
    rmap = {r[0]: r[1] for r in rets}

    # per-session grading of the daily signals (signal from close t-1)
    sessions = sorted(d for d in vix if d.isoformat() in rmap)[-days:]
    rows = []
    tp = fp = fn = tn = 0
    briers = []
    ratios = []          # rolling RVRP inputs, built in date order
    v1_sorted = sorted(v1.items())
    v1_map = dict(v1_sorted)
    for d in sessions:
        ret = rmap[d.isoformat()]
        prev = max((x for x in vix if x < d), default=None)
        if prev is None:
            continue
        v1_prev = v1_map.get(prev)
        flag = bool(v1_prev and v1_prev / SQRT252 > 1.0)
        backw = bool(v3.get(prev) and vix[prev] > v3[prev])
        y_big = abs(ret) >= 1.0
        if flag and y_big:
            tp += 1
        elif flag:
            fp += 1
        elif y_big:
            fn += 1
        else:
            tn += 1
        p_big = None
        if v1_prev:
            hist = [math.sqrt(math.pi / 2.0) * abs(rmap[dd.isoformat()])
                    / (vv / SQRT252)
                    for dd, vv in v1_sorted
                    if dd < d and dd.isoformat() in rmap and vv][-252:]
            if len(hist) >= 100:
                sig_adj = (v1_prev / SQRT252) * (sum(hist) / len(hist))
                p_big = 2 * _norm_cdf(-1.0 / sig_adj)
                briers.append((p_big - (1.0 if y_big else 0.0)) ** 2)
        rows.append({"d": d.isoformat(), "ret": round(ret, 2),
                     "flag_vix1d": flag, "backwardation": backw,
                     "y_big": y_big, "p_big_adj": p_big,
                     "grade": ("hit" if flag and y_big else
                               "false_alarm" if flag else
                               "missed" if y_big else "clear")})

    # flow-spike grading from the committed baseline (has realized fwd via CSV
    # order: recompute z inside the window; fwd not in CSV -> grade spikes by
    # the DAILY close-to-close move as proxy and label it as such)
    hist = _baseline_rows()
    spike_days = big_on_spike = 0
    nonspike_days = big_on_nonspike = 0
    for i, r in enumerate(hist):
        if i < TRAIL:
            continue
        prior = hist[i - TRAIL:i]
        pz = _z(r["putv"], [p2["putv"] for p2 in prior])
        tz = _z(r["totv"], [p2["totv"] for p2 in prior])
        ret = rmap.get(r["d"].isoformat())
        if ret is None:
            continue
        if (pz or 0) > 2 or (tz or 0) > 2:
            spike_days += 1
            big_on_spike += int(abs(ret) >= 1.0)
        else:
            nonspike_days += 1
            big_on_nonspike += int(abs(ret) >= 1.0)

    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tp / (tp + fn) if (tp + fn) else None
    return _scrub({
        "window_sessions": len(rows),
        "flag_vix1d": {
            "precision": prec, "recall": rec,
            "backtest_precision": 0.428, "backtest_recall": 0.680,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        },
        "calibration": {
            "brier_p_big_adj": (sum(briers) / len(briers)) if briers else None,
            "backtest_brier": 0.168, "n": len(briers),
        },
        "flow_spike": {
            "big_move_rate_on_spike": (big_on_spike / spike_days) if spike_days else None,
            "big_move_rate_otherwise": (big_on_nonspike / nonspike_days) if nonspike_days else None,
            "backtest_rates": [0.286, 0.121],
            "n_spike_days": spike_days,
            "note": "graded on daily close-to-close move (proxy); the "
                    "registered study graded clock-to-close",
        },
        "recent": rows[-20:],
        # ---- dynamic health: pre-registered degrade/promote rules ----------
        # A signal is DEGRADED when its live stats fall materially below the
        # backtest band over a meaningful window — the page then downgrades it
        # visually and it stops being treated as deployable. Rules are fixed
        # here, not tuned: they were chosen before observing live data.
        "health": _health(rows, prec, rec,
                          (sum(briers) / len(briers)) if briers else None,
                          (big_on_spike / spike_days) if spike_days else None,
                          (big_on_nonspike / nonspike_days) if nonspike_days else None),
        "promotion": _promotion(hist, vix),
    })


HEALTH_RULES = {
    # live precision may run this far under the backtest before degrading
    "flag_precision_tolerance": 0.15,
    "flag_min_flags": 15,           # need at least this many live flags to judge
    "brier_tolerance": 0.05,
    "spike_min_lift": 1.3,          # spike-day rate must stay ≥1.3x non-spike
    "spike_min_days": 10,
}


def _health(rows, prec, rec, brier, spike_rate, nonspike_rate) -> dict:
    R = HEALTH_RULES
    out = {}
    n_flags = sum(1 for r in rows if r["flag_vix1d"])
    if n_flags < R["flag_min_flags"] or prec is None:
        out["flag_vix1d"] = {"status": "warming_up", "n": n_flags}
    elif prec < 0.428 - R["flag_precision_tolerance"]:
        out["flag_vix1d"] = {"status": "DEGRADED",
                             "why": f"live precision {prec:.0%} vs 42.8% band"}
    else:
        out["flag_vix1d"] = {"status": "sharp"}
    if brier is None:
        out["calibration"] = {"status": "warming_up"}
    elif brier > 0.168 + R["brier_tolerance"]:
        out["calibration"] = {"status": "DEGRADED",
                              "why": f"Brier {brier:.3f} vs 0.168 band"}
    else:
        out["calibration"] = {"status": "sharp"}
    if spike_rate is None or nonspike_rate is None or nonspike_rate == 0:
        out["flow_spike"] = {"status": "warming_up"}
    elif spike_rate / nonspike_rate < R["spike_min_lift"]:
        out["flow_spike"] = {"status": "DEGRADED",
                             "why": f"lift {spike_rate/nonspike_rate:.2f}x < {R['spike_min_lift']}x"}
    else:
        out["flow_spike"] = {"status": "sharp",
                             "lift": round(spike_rate / nonspike_rate, 2)}
    # backwardation & double_floor are long-horizon rules re-validated in the
    # research repo, not gradeable on a 120-session window — marked static.
    out["backwardation"] = {"status": "static (re-validated in research repo)"}
    out["double_floor"] = {"status": "static (re-validated in research repo)"}
    return out


# Pre-registered promotion threshold for the squeeze tell (set 2026-08-12,
# BEFORE the sample matured): promote to deployable only at >=100 quiet
# sessions AND top-vs-bottom decile t >= 2 in the research harness.
PROMOTION_QUIET_NEEDED = 100


def _promotion(flow_hist: list, vix: dict) -> dict:
    quiet = 0
    for r in flow_hist:
        prev = max((d for d in vix if d < r["d"]), default=None)
        if prev and vix[prev] < QUIET_VIX:
            quiet += 1
    return {"squeeze_tell": {
        "quiet_sessions_have": quiet,
        "quiet_sessions_needed": PROMOTION_QUIET_NEEDED,
        "rule": "promote only at ≥100 quiet sessions AND decile t ≥ 2 "
                "(pre-registered 2026-08-12)",
    }}
