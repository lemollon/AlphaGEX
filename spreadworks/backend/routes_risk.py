"""Risk Advisor — read-only advisory endpoints. ADVISORY ONLY: no bot reads this.

Signal stack (validated 2026-08-12, ironforge-data/risk_advisor — every claim
pre-registered and backtested; see trials_registry.md there):

  DEPLOYABLE
    * backwardation skip     : VIX > VIX3M          (+0.09 ret/DD, 7 yrs)
    * VIX1D daily flag       : VIX1D/sqrt(252) > 1% (42.8% prec / 68% recall)
    * double_floor calm      : VVIX < 85 and VIX < 14 (0.00x next-day tail)
    * 10:00 CT flow spike    : put-vol z or total z > 2 vs trailing-63 baseline
                               (P(big rest-of-day move) 28.6% vs 12.1%, ~4.8 sigma)
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
import math
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Request
from sqlalchemy import Column, Date, DateTime, Float, BigInteger

from .db import Base, SessionLocal

router = APIRouter(prefix="/api/spreadworks/risk-advisor", tags=["Risk Advisor"])

CT = ZoneInfo("America/Chicago")
SQRT252 = 15.874507866387544
TRAIL = 63
OTM_BAND = 0.005
QUIET_VIX = 16.0
SNAPSHOT_CT = (10, 0)          # 10:00 CT — the validated clock
CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv"
BASELINE_CSV = Path(__file__).resolve().parent / "data" / "risk_flow_baseline.csv"

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
            for s in db.query(RiskFlowSnapshot).all():
                rows[s.d] = {"d": s.d, "callv": s.callv, "putv": s.putv,
                             "totv": s.totv, "otm_call_0dte": s.otm_call_0dte}
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


async def _capture_snapshot(request: Request) -> RiskFlowSnapshot | None:
    """Lazily capture today's 10:00 CT flow snapshot from Tradier (once)."""
    if SessionLocal is None:
        return None
    today = datetime.now(CT).date()
    db = SessionLocal()
    try:
        row = db.get(RiskFlowSnapshot, today)
        if row:
            return row
        now_ct = datetime.now(CT)
        if (now_ct.hour, now_ct.minute) < SNAPSHOT_CT or now_ct.weekday() >= 5:
            return None
        async with _snapshot_lock:
            row = db.get(RiskFlowSnapshot, today)
            if row:
                return row
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
            row = RiskFlowSnapshot(d=today, captured_at=datetime.now(CT),
                                   callv=callv, putv=putv, totv=callv + putv,
                                   otm_call_0dte=otm0, spot=spot)
            db.add(row)
            db.commit()
            return row
    except Exception:
        return None
    finally:
        db.close()


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
    flow = {"status": "pre-snapshot (captured at first request ≥10:00 CT)"
            if snap is None else "snapshot",
            "putv_z": None, "totv_z": None, "otm_call_0dte_z": None,
            "spike": None}
    if snap is not None:
        pz = _z(snap.putv, [r["putv"] for r in prior])
        tz = _z(snap.totv, [r["totv"] for r in prior])
        oz = _z(snap.otm_call_0dte, [r["otm_call_0dte"] for r in prior])
        flow.update({"status": "snapshot",
                     "captured_at": snap.captured_at.isoformat(),
                     "putv_z": pz, "totv_z": tz, "otm_call_0dte_z": oz,
                     "spike": bool((pz or 0) > 2 or (tz or 0) > 2)})

    risk_off = backwardation or flag_vix1d or bool(flow["spike"])
    return {
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
        "headline": ("RISK-OFF: stand down / reduce" if risk_off else
                     ("CALM FLOOR: safest premium-selling state" if double_floor
                      else "NORMAL")),
        "advisory_only": True,
    }


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
    return {"days": out[-days:]}
