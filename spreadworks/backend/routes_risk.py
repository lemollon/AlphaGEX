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
import logging
import math
from datetime import datetime, date, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Request
from sqlalchemy import Column, Date, DateTime, Float, BigInteger, Integer, String

from .db import Base, SessionLocal

router = APIRouter(prefix="/api/spreadworks/risk-advisor", tags=["Risk Advisor"])

logger = logging.getLogger(__name__)

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

# 🚨 TWO WINDOWS ON PURPOSE — they are not the same question.
#
# ROLLING_WINDOW_CT above is the ALERT window: registry #39 was validated on
# 10:36-14:00 and its 1.53x lift is measured there. Widening it would change a
# rule that was measured, so it does not move.
#
# ROLLING_LOG_WINDOW_CT is the OBSERVABILITY window: which minutes get written
# to the tape. Until 2026-08-19 these were the same value, so 41% of every
# session (08:30-10:36 and 14:00-15:00) had no flow reading recorded at all —
# including the last hour, when 0DTE gamma peaks and EBB settles at the close.
# That was never a data limit; the baseline file simply stopped at 900.
#
# A session you cannot replay is one you cannot improve — the whole reason
# risk_session_log exists. Recording is cheap and changes no behaviour;
# alerting is a rule and stays where it was measured.
ROLLING_LOG_WINDOW_CT: tuple[tuple[int, int], tuple[int, int]] = ((8, 31), (14, 59))
# --- Two-stage confirmation watcher (validated 2026-08-18) -------------------
# Stage 1 (10:00 CT): the put/call MIX is extreme -> a bigger-than-normal move
#   is coming, but the direction is a coin flip (see _pc_z's docstring).
# Stage 2 (intraday): wait for the market to pick a side, then say so.
#
# Measured over 904 sessions (bt_spy minute prices, 2023-01-03 -> 2026-08-11),
# pooling DOWN breaks and UP breaks. "Continues" = price keeps moving in the
# confirmed direction from the confirmation minute to the close.
#
#   price confirmation alone, no flow flag   n=916   49.8%   <- coin flip
#   flow flag alone at 10:00                 n= 37   coin flip on direction
#   FLAG then CONFIRMATION                   n= 95   63.2%   z = +2.61
#
# Neither ingredient works alone; the interaction is the signal. Robust across
# every confirmation threshold tried (0.10-0.30% -> z +2.37..+2.91), positive
# in all four years, and SYMMETRIC (66.7% on down breaks, 67.6% on up breaks at
# the 0.25% cut) — symmetry matters because the two sides are disjoint samples.
#
# 🚨 This is the leg that answers "why did nobody call the 2026-08-17 slide".
# Replayed on that session it confirms DOWN at 11:55 CT / 774.68 with $2.00 of
# the $3.00 move still ahead ($2.17 to the low). The 10:00 snapshot alone never
# could have — it had no direction to give.
#
# 0.10% chosen over the marginally stronger 0.15% cut (z +2.91) deliberately:
# it fires at a median 10:30 CT vs 10:40, and on a two-stage signal the whole
# point of stage 2 is how much runway is left when it speaks.
CONFIRM_ARM_Z = 1.5            # stage-1 put/call z that arms the watcher
CONFIRM_MOVE_PCT = 0.10        # stage-2 move beyond the 10:00 level, %
CONFIRM_WINDOW_CT: tuple[tuple[int, int], tuple[int, int]] = ((10, 10), (14, 0))
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


class RiskSessionLog(Base):
    """APPEND-ONLY intraday tape — one row per 10-minute slot per session.

    🚨 THIS EXISTS BECAUSE THE 2026-08-17 POST-MORTEM ALMOST HAD NOTHING TO
    READ. `risk_flow_rolling_state` keeps a single row per session and
    overwrites it on every poll, so the only surviving evidence of what the
    watcher saw during a 3-point slide was its 14:00 CT reading — long after
    the move was over. A signal you cannot replay is a signal you cannot
    improve, and it is also one you cannot draw.

    Keyed on (d, minute_ct) so both writers — the confirmation watcher, which
    has spot, and the rolling flow watcher, which has the z-scores — can fill
    their own columns in the same slot without racing or duplicating. Missing
    columns stay NULL; a gap in the tape is real information (the poll failed)
    and must not be back-filled with a neighbour's value.
    """
    __tablename__ = "risk_session_log"
    d = Column(Date, primary_key=True)
    minute_ct = Column(Integer, primary_key=True)   # CT minute-of-day
    spot = Column(Float)
    roll_putv_z = Column(Float)
    roll_totv_z = Column(Float)
    # 🚨 Added 2026-08-19. The first two grade LEVEL, which is exactly the
    # pair that was correctly quiet at 10:00 CT on 08-17 (+0.58 / -0.45) while
    # the MIX printed +2.72. The fixed clocks were taught to divide them the
    # next day; this 10-minute tape was not, so it carried the pre-08/18
    # metric all session. See _pc_z.
    roll_pc_z = Column(Float)


class RiskConfirmState(Base):
    """Two-stage confirmation watcher — one row per session.

    Holds the 10:00 CT reference price plus the running session extremes, so
    "is this a NEW session low/high" is answerable from a 10-minute poll
    without re-pulling intraday history. Additive table: nothing else reads it,
    so a cold prod database just starts filling it on the next deploy.

    🚨 `fired_*` and `close_spot` exist so every live firing lands in a row
    with its own outcome attached. The backtest that justifies this signal is
    n=95 across 4 years; the only way that number improves is if the live
    firings are recorded with what happened next, rather than being reconstructed
    later from a log that overwrote itself (which is exactly why the 2026-08-17
    post-mortem could not see what the rolling z did during the slide).
    """
    __tablename__ = "risk_confirm_state"
    d = Column(Date, primary_key=True)
    ref_spot = Column(Float)          # 10:00 CT reference
    run_min = Column(Float)           # session low seen since the reference
    run_max = Column(Float)           # session high seen since the reference
    armed = Column(String(8))         # 'yes' / 'no' — stage-1 flow flag
    putcall_z = Column(Float)         # stage-1 z that armed it
    fired_dir = Column(String(4))     # 'DOWN' / 'UP' / None
    fired_at = Column(DateTime)
    fired_spot = Column(Float)
    close_spot = Column(Float)        # filled after the close → outcome


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


def _pc(r) -> float | None:
    """Put/call VOLUME RATIO for a snapshot or baseline row.

    Call volume is always `totv - putv`, so this needs NO new capture — both
    numbers have sat side by side in every snapshot and baseline row since the
    first one. Accepts a dict (baseline/snapshot) or an ORM row.
    """
    putv = r["putv"] if isinstance(r, dict) else r.putv
    totv = r["totv"] if isinstance(r, dict) else r.totv
    if putv is None or totv is None:
        return None
    callv = totv - putv
    if callv <= 0:
        return None
    return putv / callv


def _pc_z(cur: dict, prior: list[dict]) -> float | None:
    """Trailing-63 z of the put/call ratio.

    🚨 THIS IS THE LEG THAT WAS MISSING ON 2026-08-17. The two shipped legs
    grade put volume and total volume as LEVELS and both were correctly quiet
    that morning (putv z +0.58, totv z -0.45, neither near the >2 trigger) —
    there was no put spike. The information was in the MIX: the ratio printed
    1.487, **z = +2.72, the highest of the trailing 63 sessions** and the 98th
    percentile of all 970 baseline sessions, at 10:00 CT — 90 minutes before
    SPY slid 775.50 -> 772.51 and five minutes before EBB sold a put spread
    into it. We stored both numbers and never divided them.

    Measured over 896 sessions (2023-01-03 -> 2026-08-11), 10:00 CT clock,
    outcome = |move from the clock to the close| >= 0.5%:

        base rate (all sessions)      27.2%
        ratio z > 2   (n=37)          56.8%   2.08x   <- this
        putv  z > 2   (n=42, shipped) 47.6%   1.75x
        totv  z > 2   (n=32, shipped) 31.2%   1.15x

    z = 4.03, one-sided binomial p = 1.5e-4 (1.2e-3 after Bonferroni over the
    eight variants tried), and positive in all four years (2.27 / 1.61 / 1.90
    / 2.90x). For scale, the rolling watcher (registry #39) shipped on 1.53x.

    🚨🚨 IT IS A BIG-MOVE FLAG, NOT A DOWN-MOVE FLAG. On the 37 firings
    P(down >= 0.5%) is 24.3% against P(up >= 0.5%) of 32.4% — the UPSIDE tail
    is the larger one — and P(down at all) is 45.8% vs a 45.4% base, i.e. a
    coin flip. Simulated against EBB's own structure the spot-2 short strike
    is breached 24.3% vs 18.9% base: 1.29x on n=37, NOT significant. So this
    warns and sizes; it must never be read as bearish and must not gate a bot.
    """
    cur_pc = _pc(cur)
    if cur_pc is None:
        return None
    hist = [x for x in (_pc(r) for r in prior) if x is not None]
    return _z(cur_pc, hist)


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


def session_log_write(d: date, now: datetime, *, spot: float | None = None,
                      roll_putv_z: float | None = None,
                      roll_totv_z: float | None = None,
                      roll_pc_z: float | None = None) -> None:
    """Append (or fill) this session's 10-minute tape slot. Never raises —
    the tape is a record, and losing a slot must never take down the poll
    that was trying to write it.

    Only writes the fields it was given, so two callers can share a slot.
    Deliberately does NOT overwrite a value that is already there: within one
    slot the first reading is the one that matches the alert that fired from
    it, and a later re-write would quietly desync the tape from the push.
    """
    if SessionLocal is None:
        return
    slot = (now.hour * 60 + now.minute) // 10 * 10
    db = SessionLocal()
    try:
        row = db.get(RiskSessionLog, (d, slot))
        if row is None:
            row = RiskSessionLog(d=d, minute_ct=slot)
            db.add(row)
        if spot is not None and row.spot is None:
            row.spot = spot
        if roll_putv_z is not None and row.roll_putv_z is None:
            row.roll_putv_z = roll_putv_z
        if roll_totv_z is not None and row.roll_totv_z is None:
            row.roll_totv_z = roll_totv_z
        if roll_pc_z is not None and row.roll_pc_z is None:
            row.roll_pc_z = roll_pc_z
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def session_log_read(d: date) -> list[dict]:
    """The session's tape, oldest first. Empty list on any failure — a page
    that cannot draw a chart still has to render its state cards."""
    if SessionLocal is None:
        return []
    db = SessionLocal()
    try:
        rows = (db.query(RiskSessionLog)
                  .filter(RiskSessionLog.d == d)
                  .order_by(RiskSessionLog.minute_ct).all())
        return [{"minute_ct": r.minute_ct, "spot": r.spot,
                 "roll_putv_z": r.roll_putv_z, "roll_totv_z": r.roll_totv_z,
                 "roll_pc_z": r.roll_pc_z}
                for r in rows]
    except Exception:
        return []
    finally:
        db.close()


def confirm_step(d: date, now: datetime, spot: float, armed: bool,
                 pcz: float | None) -> dict | None:
    """Advance the two-stage watcher one poll. Returns a dict WHEN IT FIRES,
    else None. Safe to call on unflagged days — it still tracks the extremes so
    a day that arms late (the 10:00 snapshot can be captured any time in its
    10:00-10:35 window) has a usable reference.

    Fires at most once per session, in the first direction confirmed.
    """
    if SessionLocal is None or not spot:
        return None
    db = SessionLocal()
    try:
        row = db.get(RiskConfirmState, d)
        if row is None:
            row = RiskConfirmState(d=d, ref_spot=spot, run_min=spot,
                                   run_max=spot)
            db.add(row)
        row.armed = "yes" if armed else "no"
        row.putcall_z = pcz
        if row.ref_spot is None:
            row.ref_spot = spot
        row.run_min = min(row.run_min if row.run_min is not None else spot, spot)
        row.run_max = max(row.run_max if row.run_max is not None else spot, spot)

        out = None
        if armed and row.fired_dir is None and row.ref_spot:
            move = (spot - row.ref_spot) / row.ref_spot * 100.0
            # "at a session extreme" — the break has to BE the low/high, not
            # just be below the reference, or a day that gapped down at 10:05
            # and chopped sideways would fire on every poll.
            at_low = spot <= (row.run_min or spot) * 1.0005
            at_high = spot >= (row.run_max or spot) * 0.9995
            if move <= -CONFIRM_MOVE_PCT and at_low:
                row.fired_dir = "DOWN"
            elif move >= CONFIRM_MOVE_PCT and at_high:
                row.fired_dir = "UP"
            if row.fired_dir:
                row.fired_at = now.replace(tzinfo=None)
                row.fired_spot = spot
                out = {"dir": row.fired_dir, "spot": spot,
                       "ref": row.ref_spot, "move_pct": move,
                       "putcall_z": pcz, "at": now}
        db.commit()
        return out
    except Exception:
        db.rollback()
        return None
    finally:
        db.close()


def confirm_record_close(d: date, close_spot: float) -> None:
    """Attach the session close to today's watcher row so the firing carries
    its own outcome. Never raises — a missing row just means no firing."""
    if SessionLocal is None:
        return
    db = SessionLocal()
    try:
        row = db.get(RiskConfirmState, d)
        if row is not None:
            row.close_spot = close_spot
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


def _latest_snapshot(d: date) -> dict | None:
    """READ-ONLY: today's stored 10:00 CT snapshot, or None.

    Deliberately never captures. The confirmation watcher polls every 10
    minutes right through the afternoon, and `_capture_snapshot` will happily
    write a row whenever it is called inside the 10:00-10:35 window — so
    calling that from a repeating job risks the exact failure the window
    guard exists to prevent (a late pull stored as if it were the 10:00
    figure, graded against a 10:00 baseline, reading as a huge false spike).
    Same validity rule as everywhere else: a row outside its window is not
    that clock's number and is treated as absent.
    """
    if SessionLocal is None:
        return None
    db = SessionLocal()
    try:
        row = db.get(RiskFlowSnapshot, d)
        if row is None or not _snap_valid(row.captured_at):
            return None
        return _snap_dict(row)
    except Exception:
        return None
    finally:
        db.close()


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



def _scheduler_block() -> dict:
    """Which risk jobs are armed and when they next fire.

    Never raises: a chart losing its next-update cell is a cosmetic loss, a 500
    on /risk/state is not. An import or lookup failure reports registered=None
    (unknown), which the UI renders amber — never green, and never a guess at
    the cron time.
    """
    try:
        from .risk_alerts import scheduled_jobs
        return {"scheduler": scheduled_jobs()}
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_risk] scheduled_jobs failed: %r", e)
        return {"scheduler": {"registered": None, "jobs": {},
                              "reason": f"scheduled_jobs error: {e}"}}


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

        # The recipe is a SAME-DAY put spread, so its expiration is the
        # SESSION it would trade in — which is not today when today is a
        # weekend. Returning today's date there had the card announce
        # "expires TODAY (2026-08-16)" on a Sunday, an expiry that does not
        # exist, directly above its own "weekend — next window Monday" line.
        # (Market holidays are not modelled here; the phase machinery does not
        # model them either, so this stays consistent with the rest of the
        # module rather than inventing a half-calendar.)
        session = today
        while session.weekday() >= 5:
            session += timedelta(days=1)

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
            "expiration": session.isoformat(),
            "expires_today": session == today,
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


def _state_freshness(now_ct: datetime, asof_close: date, flow: dict,
                     flow_rolling: dict | None) -> dict:
    """Is what this page is showing actually current?

    Three legs, graded independently — they fail in different ways:

      close   the VIX/term-structure close the verdict is built from. Correct
              when it equals the last weekday before today; a regime call from
              the prior close is BY DESIGN, not staleness.
      flow    the 10:00 CT snapshot. Either it captured today or it did not.
      rolling the */10 watcher. Only meaningful inside its window — a gap at
              11:00 is a fault, a gap at 16:00 is just the window being over.

    Never raises: a page that cannot compute its own freshness must still
    render, and must say "unknown" rather than imply fresh.
    """
    out: dict = {"state": "UNKNOWN", "detail": None, "legs": []}
    try:
        today = now_ct.date()
        expected = today - timedelta(days=1)
        while expected.weekday() >= 5:
            expected -= timedelta(days=1)
        # Before the close the prior session is still the right basis; after
        # it, today's own close is what should be there.
        behind = _sessions_behind(asof_close, expected)
        close_ok = behind is not None and behind <= 0
        out["expected_close"] = expected.isoformat()
        out["asof_close"] = asof_close.isoformat()
        out["close_sessions_behind"] = behind
        out["legs"].append({
            "key": "close", "label": "VIX / term structure",
            "value": asof_close.isoformat(),
            "ok": close_ok,
            "note": ("prior close, as designed" if close_ok else
                     f"{behind} session(s) behind {expected.isoformat()}"
                     if behind is not None else "unknown"),
        })

        cap = (flow or {}).get("captured_at")
        cap_today = bool(cap and str(cap)[:10] == today.isoformat())
        weekend = now_ct.weekday() >= 5
        due = (now_ct.hour, now_ct.minute) >= SNAPSHOT_CT and not weekend
        out["legs"].append({
            "key": "flow", "label": "10:00 flow snapshot",
            "value": (str(cap)[11:16] + " CT") if cap_today else None,
            "ok": cap_today or not due,
            "note": ("captured today" if cap_today else
                     "not due until 10:00 CT" if not due else
                     "DUE BUT NOT CAPTURED"),
        })

        roll_cap = (flow_rolling or {}).get("captured_at")
        age = None
        if roll_cap:
            try:
                rc = datetime.fromisoformat(str(roll_cap))
                if str(roll_cap)[:10] == today.isoformat():
                    age = int((now_ct.replace(tzinfo=None) - rc).total_seconds() // 60)
            except Exception:                                # noqa: BLE001
                age = None
        t = (now_ct.hour, now_ct.minute)
        in_roll = (not weekend) and ROLLING_WINDOW_CT[0] <= t <= ROLLING_WINDOW_CT[1]
        # >15 min inside a */10 window means at least one poll was missed.
        roll_ok = (not in_roll) or (age is not None and age <= 15)
        out["legs"].append({
            "key": "rolling", "label": "rolling flow watcher",
            "value": (str(roll_cap)[11:16] + " CT") if age is not None else None,
            "ok": roll_ok,
            "note": (f"{age}m ago" if age is not None and roll_ok else
                     f"NO READING FOR {age}m" if age is not None else
                     "outside its window" if not in_roll else "NO READING TODAY"),
        })

        bad = [l for l in out["legs"] if l["ok"] is False]
        if not bad:
            out["state"] = "CURRENT"
            out["detail"] = "every input is as current as it should be right now"
        else:
            out["state"] = "STALE"
            out["detail"] = "; ".join(f"{l['label']}: {l['note']}" for l in bad)
    except Exception as e:                                   # noqa: BLE001
        out["detail"] = f"freshness unavailable: {e!r}"
    return out


def _sessions_behind(actual: date, expected: date) -> int | None:
    """Weekday sessions `actual` sits behind `expected`. Negative means ahead
    (today's close already stored, which is fine, not stale)."""
    try:
        if actual == expected:
            return 0
        step = 1 if actual < expected else -1
        n, d = 0, actual
        while d != expected and abs(n) < 40:
            d += timedelta(days=step)
            if d.weekday() < 5:
                n += step
        return n
    except Exception:                                        # noqa: BLE001
        return None


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
            "otm_call_0dte_z": None, "putcall_z": None, "spike": None,
            "flagged": None}
    if snap is not None:
        pz = _z(snap["putv"], [r["putv"] for r in prior])
        tz = _z(snap["totv"], [r["totv"] for r in prior])
        oz = _z(snap["otm_call_0dte"], [r["otm_call_0dte"] for r in prior])
        cz = _pc_z(snap, prior)
        flow.update({"captured_at": snap["captured_at"].isoformat(),
                     "putv_z": pz, "totv_z": tz, "otm_call_0dte_z": oz,
                     "putcall_z": cz,
                     "spike": bool((pz or 0) > 2 or (tz or 0) > 2
                                   or (cz or 0) > 2),
                     # `flagged` arms the intraday CONFIRMATION watcher; it
                     # uses the looser 1.5 cut the two-stage test was measured
                     # at, while `spike` keeps the shipped >2 alert semantics.
                     "flagged": bool((cz or 0) > CONFIRM_ARM_Z)})

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

    # ── INTRADAY ESCALATION ──────────────────────────────────────────────────
    # 🚨 THREE VALIDATED SIGNALS USED TO ALERT YOUR PHONE AND NEVER MOVE THIS
    # PAGE. `action` was computed once from prior closes plus the single 10:00
    # snapshot and then frozen for the session, so a 13:30 spike could push a
    # Discord alert while /risk still read NORMAL. Each of these is already
    # pre-registered and backtested:
    #
    #   12:00 CT re-check   P(|move to close| >= 0.5%) 29.3% vs 17.0% base
    #   13:30 CT re-check                              17.0% vs  8.4% base
    #   rolling watcher     (registry #39, */10 CT)    34.2% vs 22.4% base
    #
    # ⛔ NOT DOUBLE-COUNTED. rolling_flow_check() already suppresses itself when
    # a fixed clock has alerted a spike the same day, so these are disjoint by
    # construction upstream — the page must not re-add what the watcher has
    # already withheld. It reads `fired_today`, which is that dedup'd flag.
    pm_spike = [c for c, e in (flow_pm or {}).items() if e.get("spike")]
    rolling_fired = bool((flow_rolling or {}).get("fired_today"))
    intraday_flags = list(pm_spike) + (["rolling"] if rolling_fired else [])

    risk_off = (backwardation or flag_vix1d or bool(flow["spike"])
                or bool(intraday_flags))
    # explicit whitelist action (v2 §7.1): the ONLY instruction this endpoint
    # gives. "normal" on calm/no-signal days — the advisor never says "sell
    # more"; sizing up is not risk management.
    action = ("stand_down" if (backwardation and flag_vix1d) else
              "skip_entry" if risk_off else "normal")
    assert action in ACTION_WHITELIST

    # ⛔ RATCHET, NEVER OSCILLATE. A verdict that reads RISK-OFF at 12:06 and
    # NORMAL again at 12:16 is worse than one that never moved — the alert has
    # already gone out and the reader cannot unsee it. Escalation within a
    # session is one-way: once an intraday clock has fired, it stays fired for
    # the rest of the day (the underlying flags are day-scoped and only ever
    # turn on), and this records WHICH clock did it so the page can say so.
    escalated_by = None
    if intraday_flags and not (backwardation or flag_vix1d or flow["spike"]):
        # The prior-close legs were all quiet; this verdict exists only because
        # of an intraday firing, which is exactly the case the page could not
        # previously express.
        escalated_by = intraday_flags
    # ── FRESHNESS. 🚨 The page could not previously tell you whether it was
    # showing today's read or a leftover, which is the same defect /session
    # shipped and then fixed on 08-18.
    #
    # 🚨 THE TRAP: this verdict is SUPPOSED to be built from the PRIOR close.
    # A naive "the data is a day old" badge would scream STALE every single
    # morning, and a warning that cries wolf daily is one nobody reads. So
    # staleness is measured against the EXPECTED session — the last weekday
    # before today — not against today. Same rule data_freshness() already
    # uses for the squeeze page.
    #
    # The intraday legs are graded separately and on their OWN clocks, because
    # "the VIX close is current" and "the 10:00 flow snapshot ran" are
    # different questions with different failure modes.
    _fresh = _state_freshness(datetime.now(CT), d_vix, flow, flow_rolling)

    _payload = _scrub({
        "asof_close": d_vix.isoformat(),
        "generated_at": datetime.now(CT).isoformat(),
        "freshness": _fresh,
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
        "escalated_by": escalated_by,
        "intraday_flags": intraday_flags,
        "macro": _macro_block(),
        # When the charts' inputs next move. Read from the live scheduler, not
        # from the cadence prose in the captions — that prose stays confidently
        # correct after a job dies, which is precisely the failure the charts'
        # "next update" cell exists to expose.
        "jobs": _scheduler_block(),
        # 🚨 NAME THE INTRADAY ESCALATION IN THE HEADLINE. If the page was
        # NORMAL this morning and is RISK-OFF now, the reader has to be able to
        # see that it MOVED and what moved it - otherwise a mid-session change
        # is indistinguishable from a page that always said this.
        "headline": (
            (f"RISK-OFF (escalated intraday by the {', '.join(escalated_by)} "
             f"flow check): stand down / reduce") if escalated_by else
            "RISK-OFF: stand down / reduce" if risk_off else
            ("CALM FLOOR: safest premium-selling state" if double_floor
             else "NORMAL")),
        "advisory_only": True,
    })
    try:
        from .call_log import record_call
        # 🚨 The ACTION is the call. `headline` is prose wrapped around it and
        # can change wording without the decision changing - logging that
        # instead would manufacture flips that never happened.
        record_call("risk", action,
                    detail={"headline": _payload.get("headline"),
                            "backwardation": backwardation,
                            "flag_vix1d": flag_vix1d,
                            "double_floor": double_floor,
                            "vix": vix_c, "vix1d": v1_c},
                    # The VIX close this rests on, not the moment we asked.
                    data_ts=datetime.combine(d_vix, time(15, 15)))
    except Exception:
        pass
    return _payload


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


# ---------------------------------------------------------------------------
# SESSION TAPE — the live intraday surface (/session).
#
# Everything else on the Risk page answers "what is today's regime", decided
# once from the prior close. This answers "what is happening right now", and
# it exists because the 2026-08-17 miss was invisible in real time: the
# watchers were running, but no single view put price, the flow z, the fixed
# clocks and the confirmation state on one clock. Reconstructing that session
# afterwards took four tables and an external price API.
#
# Deliberately NOT included:
#   * any gamma/GEX reading. `gamma_history` writes ~280 rows a day holding 3
#     distinct values (spot froze at 775.80 on 08-17 while SPY traded to
#     772.51). Plotting it would look authoritative and be wrong; the page
#     reports the feed as dead instead.
#   * a verdict. /risk and /squeeze own that. Two surfaces disagreeing about
#     the same call is worse than one surface.
# ---------------------------------------------------------------------------

MARKET_OPEN_CT = (8, 30)
MARKET_CLOSE_CT = (15, 0)


@router.get("/session")
async def session_tape(request: Request):
    """Live state of the current session. Cheap: reads only stored rows —
    no Tradier call — so the page can poll it every 30s without cost."""
    now_ct = datetime.now(CT)
    today = now_ct.date()
    t = (now_ct.hour, now_ct.minute)
    weekend = now_ct.weekday() >= 5
    live = (not weekend) and MARKET_OPEN_CT <= t <= MARKET_CLOSE_CT

    tape = session_log_read(today)

    # 🚨 FRESHNESS COMES FROM THE DATA, NOT THE MARKET CLOCK.
    #
    # The first version derived "LIVE" from market hours (08:30-15:00 CT). But
    # the watchers only run 10:10-14:00, so between 14:00 and the close the
    # page sat there with a green LIVE badge over a tape that had stopped 30+
    # minutes earlier. That is the same defect this page exists to catch, and
    # it shipped inside the fix for it.
    #
    # Age is measured off the newest tape row. A stall INSIDE the watcher
    # window is a genuine fault and must read differently from the window
    # simply being over, which is normal.
    now_min = now_ct.hour * 60 + now_ct.minute
    last_min = tape[-1]["minute_ct"] if tape else None
    age_min = (now_min - last_min) if last_min is not None else None
    win_open = CONFIRM_WINDOW_CT[0][0] * 60 + CONFIRM_WINDOW_CT[0][1]
    win_close = CONFIRM_WINDOW_CT[1][0] * 60 + CONFIRM_WINDOW_CT[1][1]
    in_window = (not weekend) and win_open <= now_min <= win_close

    if weekend:
        clock = {"live": False, "state": "WEEKEND", "detail": "no session today"}
    elif t < MARKET_OPEN_CT:
        clock = {"live": False, "state": "PRE-OPEN",
                 "detail": "watchers start at 10:10 CT"}
    elif now_min < win_open:
        clock = {"live": False, "state": "WAITING",
                 "detail": "market open; the watchers start at 10:10 CT"}
    elif in_window and age_min is not None and age_min > 15:
        # polls are every 10 min, so >15 means at least one was missed
        clock = {"live": False, "state": "STALLED",
                 "detail": f"no reading for {age_min} min while the watchers "
                           "should be running — treat everything below as frozen"}
    elif in_window and last_min is None:
        clock = {"live": False, "state": "NO DATA",
                 "detail": "the watchers are in their window but nothing has "
                           "been recorded yet"}
    elif in_window:
        clock = {"live": True, "state": "LIVE", "detail": None}
    else:
        clock = {"live": False, "state": "WATCHERS CLOSED",
                 "detail": "the watch window ended at 14:00 CT — this is the "
                           "final state of today's session, not a live reading"}
    clock["age_min"] = age_min
    clock["last_reading_ct"] = (f"{last_min // 60:02d}:{last_min % 60:02d}"
                                if last_min is not None else None)
    clock["window_ct"] = "10:10–14:00"
    # The tape and the confirmation watcher no longer share a window, so the
    # page has to say which is which — a single "watch window" label over two
    # different spans is how the LIVE badge lied about freshness on 08-18.
    clock["tape_window_ct"] = "08:31–14:59"

    confirm: dict = {"armed": None, "ref_spot": None, "fired_dir": None,
                     "fired_at": None, "fired_spot": None, "close_spot": None,
                     "putcall_z": None, "run_min": None, "run_max": None,
                     "arm_z": CONFIRM_ARM_Z, "move_pct": CONFIRM_MOVE_PCT}
    if SessionLocal is not None:
        try:
            db = SessionLocal()
            row = db.get(RiskConfirmState, today)
            db.close()
            if row is not None:
                confirm.update({
                    "armed": row.armed == "yes", "ref_spot": row.ref_spot,
                    "run_min": row.run_min, "run_max": row.run_max,
                    "putcall_z": row.putcall_z, "fired_dir": row.fired_dir,
                    "fired_at": row.fired_at.isoformat() if row.fired_at else None,
                    "fired_spot": row.fired_spot, "close_spot": row.close_spot,
                })
        except Exception:
            pass

    # the trigger levels, precomputed so the chart can draw them as lines
    levels = {"down": None, "up": None}
    if confirm["ref_spot"]:
        r = float(confirm["ref_spot"])
        levels = {"down": round(r * (1 - CONFIRM_MOVE_PCT / 100), 2),
                  "up": round(r * (1 + CONFIRM_MOVE_PCT / 100), 2)}

    # which fixed clocks have captured today, and did each one flag
    clocks: list[dict] = []
    snap = _latest_snapshot(today)
    prior = [r for r in _flow_history() if r["d"] < today]
    if snap is not None:
        pz = _z(snap["putv"], [r["putv"] for r in prior])
        tz = _z(snap["totv"], [r["totv"] for r in prior])
        cz = _pc_z(snap, prior)
        clocks.append({"clock": "10:00", "captured": True, "putv_z": pz,
                       "totv_z": tz, "putcall_z": cz,
                       "flagged": bool((pz or 0) > 2 or (tz or 0) > 2
                                       or (cz or 0) > 2)})
    else:
        clocks.append({"clock": "10:00", "captured": False, "putv_z": None,
                       "totv_z": None, "putcall_z": None, "flagged": None})
    for ck in PM_CLOCKS:
        hist_pm = _pm_flow_history(ck)
        prior_pm = [r for r in hist_pm if r["d"] < today]
        cur = next((r for r in hist_pm if r["d"] == today), None)
        if cur is None:
            clocks.append({"clock": ck, "captured": False, "putv_z": None,
                           "totv_z": None, "putcall_z": None, "flagged": None})
            continue
        pz = _z(cur["putv"], [r["putv"] for r in prior_pm])
        tz = _z(cur["totv"], [r["totv"] for r in prior_pm])
        cz = _pc_z(cur, prior_pm)
        clocks.append({"clock": ck, "captured": True, "putv_z": pz,
                       "totv_z": tz, "putcall_z": cz,
                       "flagged": bool((pz or 0) > 2 or (tz or 0) > 2
                                       or (cz or 0) > 2)})

    # which pushes have already gone out today
    alerts = []
    for key, label in (("risk_morning_verdict", "morning verdict"),
                       ("risk_flow_spike", "10:00 flow"),
                       ("risk_pm_1200", "12:00 re-check"),
                       ("risk_pm_1330", "13:30 re-check"),
                       ("risk_flow_rolling", "rolling flow"),
                       ("risk_confirm", "DIRECTION CONFIRMED")):
        alerts.append({"key": key, "label": label,
                       "fired": _posted_today(key, today)})

    # ── HOW FAR IS IT FROM COMMITTING, AND HOW FAR DOES IT GO AFTER
    #
    # The 08-18 page drew the two trigger lines and left the distance to be
    # eyeballed off a chart. At 11:20 CT the question is arithmetic — "is this
    # 4 cents away or 40" — and it should not require reading pixels.
    last_spot = next((r["spot"] for r in reversed(tape) if r["spot"] is not None), None)
    to_trigger: dict = {"spot": last_spot, "down": None, "up": None,
                        "down_pct": None, "up_pct": None}
    if last_spot and levels["down"] and levels["up"]:
        to_trigger.update({
            "down": round(last_spot - levels["down"], 2),
            "up": round(levels["up"] - last_spot, 2),
            "down_pct": round((last_spot - levels["down"]) / last_spot * 100, 3),
            "up_pct": round((levels["up"] - last_spot) / last_spot * 100, 3),
        })

    # Run since the confirmation, signed in the fired direction — the live
    # counterpart to the historical runway below. On 08-17 the replayed signal
    # confirmed with $2.00 of a $3.00 slide still ahead; that is the number
    # this makes visible while it is still happening.
    run_since_fire = None
    if confirm["fired_spot"] and last_spot:
        sign = 1.0 if confirm["fired_dir"] == "UP" else -1.0
        run_since_fire = {
            "pct": round(sign * (last_spot - confirm["fired_spot"])
                         / confirm["fired_spot"] * 100, 3),
            "dollars": round(sign * (last_spot - confirm["fired_spot"]), 2),
        }

    # 🚨 MAGNITUDE, not just hit rate. A 63% hit rate on a move that dies
    # instantly is not tradeable; what makes stage 2 worth acting on is that a
    # flagged break wins ~2.8x what it gives back while an unflagged one is
    # 1.05x. Computed from the same rows the decay monitor grades, so it keeps
    # updating with live sessions. See signal_calibration.runway.
    try:
        from .signal_calibration import runway as _runway, report as _report
        runway_stats = _runway(today)
    except Exception:                                        # noqa: BLE001
        runway_stats, _report = {}, None

    # The decay monitor had no UI anywhere. An advisory page that cannot say
    # whether its own rule is still passing is asking to be trusted on faith.
    calib = {}
    try:
        if _report is not None:
            r = _report(today)
            calib = {k: r.get(k) for k in
                     ("verdict", "sessions", "live_sessions", "n_armed_fired",
                      "continuation", "continuation_lcb", "base_continuation",
                      "armed_share", "stage1_lift", "window_months")}
            calib["reasons"] = (r.get("reasons") or [])[:2]
    except Exception:                                        # noqa: BLE001
        pass

    # Recent sessions — the track record, which the page could not show at all.
    history: list[dict] = []
    try:
        from .signal_calibration import SignalEval
        if SessionLocal is not None:
            db = SessionLocal()
            try:
                rows = (db.query(SignalEval)
                          .filter(SignalEval.d < today)
                          .order_by(SignalEval.d.desc()).limit(15).all())
                history = [{"d": r.d.isoformat(), "armed": bool(r.armed),
                            "pcz": r.pcz, "fired_dir": r.fired_dir or None,
                            "continued": (None if r.continued is None
                                          else bool(r.continued)),
                            "move_pct": r.move_pct} for r in rows][::-1]
            finally:
                db.close()
    except Exception:                                        # noqa: BLE001
        pass

    # 🚨 LOG THE CALL FROM THE ENDPOINT THE PAGE ACTUALLY LOADS. This was
    # attached to /calibration, which the page never calls, and it read
    # out["headline"] from a report() that has no such key - so it recorded
    # `None` from a route nobody hit. Result: zero session rows in sw_call_log
    # since it shipped, and a history feature that silently covered two
    # surfaces instead of three.
    try:
        from .call_log import record_call
        record_call("session", _session_headline(confirm),
                    detail={"armed": confirm.get("armed"),
                            "putcall_z": confirm.get("putcall_z"),
                            "fired_dir": confirm.get("fired_dir"),
                            "ref_spot": confirm.get("ref_spot")})
    except Exception:                                        # noqa: BLE001
        pass                     # instrumentation must never break the page

    return {
        "asof": now_ct.isoformat(),
        "clock": clock,
        "tape": tape,
        "confirm": confirm,
        "headline": _session_headline(confirm),
        "levels": levels,
        "to_trigger": to_trigger,
        "run_since_fire": run_since_fire,
        "runway": runway_stats,
        "calibration": calib,
        "history": history,
        "window": {
            "opens_in_min": max(0, win_open - now_min) if now_min < win_open else 0,
            "closes_in_min": max(0, win_close - now_min) if now_min <= win_close else 0,
            "open_ct": f"{win_open // 60:02d}:{win_open % 60:02d}",
            "close_ct": f"{win_close // 60:02d}:{win_close % 60:02d}",
        },
        "clocks": clocks,
        "alerts": alerts,
        "gamma_feed": {
            "usable": False,
            "reason": "gamma_history writes ~280 rows/day holding 3 distinct "
                      "values — on 2026-08-17 spot froze at 775.80 while SPY "
                      "traded to 772.51. Deliberately not plotted.",
        },
        "note": "Advisory. No bot reads this page.",
    }


def _session_headline(confirm: dict) -> str:
    """The Session page's call, as one string.

    🚨 THIS USED TO EXIST ONLY IN THE FRONTEND (SessionPage.jsx lines 168-185),
    so the call being shown lived nowhere the server could record. Logging it
    from a copy of that logic would have created a second source of truth that
    drifts apart; computing it here and letting the page render it keeps one.

    Priority order is preserved from the page: a FIRED call outranks
    everything, then armed-and-waiting, then the quiet state. Never lead with
    the quiet state while a call is live on the same page.
    """
    c = confirm or {}
    fired = c.get("fired_dir")
    if fired:
        return f"{fired} CONFIRMED"
    armed = c.get("armed")
    if armed in (True, "yes"):
        return "ARMED \u2014 WAITING FOR A SIDE"
    if armed in (False, "no"):
        return "NOT ARMED"
    return "WAITING FOR THE 10:00 SNAPSHOT"


def _posted_today(key: str, d: date) -> bool:
    """Has `key` claimed its slot today? Read-only mirror of
    risk_alerts._already_posted, kept here so this module does not import
    risk_alerts (which imports FROM here)."""
    try:
        from .models import DiscordPostLog
    except Exception:
        return False
    if SessionLocal is None:
        return False
    db = SessionLocal()
    try:
        return db.get(DiscordPostLog, (key, d)) is not None
    except Exception:
        return False
    finally:
        db.close()


@router.get("/delivery")
async def delivery_status():
    """Is Discord actually RECEIVING these alerts?

    🚨 The alert log answers a different question than people think: it records
    that a slot was CLAIMED. _post() now releases the slot when a send fails,
    but nothing surfaced WHETHER sends are succeeding — and on 2026-08-20 every
    alert was in fact failing (a NameError inside _post, swallowed by each
    job's except-and-log). Nothing on any page would have shown that.

    Reports what is CONFIGURED and what actually HAPPENED on the last send.
    Never reveals a webhook URL, only whether one is present.
    """
    import os
    from .risk_alerts import _LAST_DELIVERY

    def configured(name: str) -> bool:
        return bool((os.getenv(name) or "").strip())

    sinks = {
        "risk_advisor_webhook": configured("RISK_ADVISOR_DISCORD_WEBHOOK"),
        "fleet_webhook_fallback": configured("DISCORD_WEBHOOK_URL"),
        "phone_webhook": configured("RISK_PHONE_WEBHOOK"),
        "ntfy_topic": configured("RISK_NTFY_TOPIC"),
    }
    return {
        # the alert channel falls back to the fleet webhook, so either works
        "can_alert": sinks["risk_advisor_webhook"] or sinks["fleet_webhook_fallback"],
        "can_reach_phone": sinks["phone_webhook"],
        "sinks": sinks,
        "last_delivery": dict(_LAST_DELIVERY),
        "note": ("A claimed slot is NOT proof of delivery. A failed send "
                 "releases its slot so the next poll retries; the outcome of "
                 "the most recent attempt is above."),
    }


@router.get("/calibration")
async def calibration(request: Request):
    """Is the signal still working? Scorecard over a rolling window, graded
    against thresholds pre-registered on 2026-08-18 before any live firing
    existed. Read-only — the nightly job is what enforces."""
    from .signal_calibration import report
    out = report()
    return out


@router.get("/tape-shape")
def tape_shape():
    """The base case every verdict on this app sits on top of.

    🚨 THE PAGES NEVER SAID WHICH WAY THE TAPE LEANS. Risk, Session and Squeeze
    all report deviations from a baseline and none of them ever stated the
    baseline. Without it "no edge today" reads as "nothing is knowable", when in
    fact the unconditional tape has a real and free directional tilt.

    ⛔ AND IT KILLS A STYLIZED FACT I ASSERTED FROM MEMORY. Equity indices are
    supposed to drift up and CRASH down. Measured here, the crash half is not
    true for this era: daily skew is POSITIVE, the largest single move in the
    sample is an up day, and the 5th/95th percentiles are symmetric to within
    2%. Selling puts is aligned with the DRIFT, not compensated for a fat left
    tail - and a page that claimed otherwise would have someone sizing for a
    crash premium that this sample does not pay.

    Computed live from sw_spy_daily so it cannot go stale, and it reports n so
    a thin window is visible rather than implied.
    """
    if SessionLocal is None:
        return {"status": "unavailable", "reason": "no database"}
    # ORM, not raw SQL: this module has no `text` import and adding one just
    # for this would be the only raw query in the file.
    from .call_log import SpyDaily
    db = SessionLocal()
    try:
        rows = [(r.trade_date, r.close) for r in
                db.query(SpyDaily).filter(SpyDaily.close.isnot(None))
                  .order_by(SpyDaily.trade_date).all()]
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_risk] tape_shape query failed: %r", e)
        return {"status": "unavailable", "reason": str(e)}
    finally:
        db.close()

    rets = []
    for a, b in zip(rows, rows[1:]):
        if a[1] and b[1]:
            rets.append(100.0 * (b[1] - a[1]) / a[1])
    n = len(rets)
    # ⛔ Below ~120 sessions the tail cells are single digits and the whole
    # panel would be quoting noise. Say so rather than render it.
    if n < 120:
        return {"status": "thin", "n": n,
                "reason": f"only {n} sessions stored; needs 120+ to be worth quoting"}

    srt = sorted(rets)
    def pctl(p):
        return srt[min(n - 1, max(0, int(round(p * (n - 1)))))]
    up = [r for r in rets if r > 0]
    dn = [r for r in rets if r < 0]
    share = lambda f: sum(1 for r in rets if f(r)) / n
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / (n - 1)
    sd = var ** 0.5
    skew = (sum(((r - mean) / sd) ** 3 for r in rets) * n / ((n - 1) * (n - 2))) if sd else None

    p_up = len(up) / n
    p_up50, p_dn50 = share(lambda r: r >= 0.5), share(lambda r: r <= -0.5)
    p95, p05 = pctl(0.95), pctl(0.05)

    # ── HOW MUCH OPTIONS OVERPRICE THE MOVE ──────────────────────────────────
    # 🚨 STATED WITHOUT A SCALING FUDGE. Comparing realised RANGE to an implied
    # move needs a ~1.6x range-to-sd convention, which is an assumption a reader
    # cannot check. |close-to-close| against the implied 1-sigma is
    # apples-to-apples: no constant, and it has a free null - a fairly priced
    # market finishes inside 1 sigma about 68% of the time. Anything well above
    # that is the seller's edge, measured rather than asserted.
    vrp = None
    try:
        from sqlalchemy import text as _sql_text
        db2 = SessionLocal()
        try:
            rows2 = db2.execute(_sql_text(
                "SELECT s.trade_date, s.close, v.vix "
                "FROM sw_spy_daily s JOIN sw_vix_daily v ON v.trade_date = s.trade_date "
                "WHERE s.close IS NOT NULL AND v.vix IS NOT NULL "
                "ORDER BY s.trade_date")).fetchall()
        finally:
            db2.close()
        pairs = []
        for a, b in zip(rows2, rows2[1:]):
            if a[1] and b[1] and b[2]:
                mv = abs(100.0 * (float(b[1]) - float(a[1])) / float(a[1]))
                sd1 = float(b[2]) / (252 ** 0.5)
                if sd1 > 0:
                    pairs.append((mv, sd1))
        if len(pairs) >= 120:
            ratios = sorted(m / s_ for m, s_ in pairs)
            k = len(ratios)
            inside = sum(1 for m, s_ in pairs if m < s_) / k
            vrp = {
                "n": k,
                "mean_ratio": sum(ratios) / k,
                "median_ratio": ratios[k // 2],
                "pct_inside_1sd": inside,
                "fair_inside": 0.683,
                "edge_pts": 100.0 * (inside - 0.683),
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("[routes_risk] vrp block failed: %r", e)
        vrp = None

    return {
        "status": "ok",
        "n": n,
        "first": str(rows[0][0]),
        "last": str(rows[-1][0]),
        "p_up_day": p_up,
        "mean_ret": mean,
        "mean_up_day": (sum(up) / len(up)) if up else None,
        "mean_dn_day": (sum(dn) / len(dn)) if dn else None,
        "p_up_50": p_up50,
        "p_dn_50": p_dn50,
        # The headline asymmetry: how much likelier an ordinary up move is.
        "drift_ratio": (p_up50 / p_dn50) if p_dn50 else None,
        "p95": p95,
        "p05": p05,
        # >1 means the LEFT tail is fatter. Around 1 means symmetric - which is
        # what this era actually shows, contradicting the textbook.
        "tail_ratio": (abs(p05) / p95) if p95 else None,
        "skew": skew,
        "vrp": vrp,
        "best_day": max(rets),
        "worst_day": min(rets),
    }
