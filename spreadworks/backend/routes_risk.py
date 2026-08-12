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
# Capture must happen NEAR the clock or the stored volumes are not the 10:00
# figure at all. The first deploy captured at 18:18 CT and stored end-of-day
# cumulative volume labeled as the 10:00 snapshot — vs a 10:00 baseline that
# reads as a huge false spike. Window enforced on WRITE and on READ, so any
# polluted row is neutralized without a migration.
SNAPSHOT_WINDOW_END_CT = (10, 35)
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
            for r in db.query(RiskFlowSnapshot).all():
                if not _snap_valid(r.captured_at):
                    continue        # late captures are not 10:00 figures
                rows[r.d] = {"d": r.d, "callv": r.callv, "putv": r.putv,
                             "totv": r.totv, "otm_call_0dte": r.otm_call_0dte}
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


_live_cache: dict = {}
_LIVE_TTL = 60
_intraday_cache: dict = {}
_INTRADAY_TTL = 60
_spyhist_cache: dict = {}
_SPYHIST_TTL = 1800
GRADES = [(0.75, "stand_down"), (0.55, "hedge"), (0.35, "reduce_size")]


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

    live = await _live_quote(request)
    if live and v1_c:
        implied = v1_c / SQRT252
        live["expected_move_pct"] = implied
        live["move_budget_used"] = abs(live.get("chg_pct", 0)) / implied if implied else None
    rets = await _spy_daily_rets(request)
    outlook = _outlook(vix_c, v9_c, v1, rets)

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
        "live": live,
        "outlook": outlook,
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

        payload = {"bars": bars, "prev_close": prev_close, "band_pct": band_pct,
                   "snapshot_t": "10:00", "status": "ok",
                   "generated_at": now.isoformat()}
        _intraday_cache["v"] = (now, payload)
        return payload
    except Exception:
        return {"bars": [], "status": "intraday unavailable"}


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
    return {
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
    }


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
