"""Live volatility-index + dealer-gamma market-structure engine.

This module is intentionally separate from the backtested daily SQUEEZE signal.
It provides intraday CONTEXT for reports using one canonical live chain source
(ORATS one-minute chain) and fresh Tradier index quotes.

Key rules:
- Never mix providers inside one gamma snapshot.
- Never reuse stale quotes silently.
- Gamma is estimated dealer exposure, not observed dealer inventory.
- ORATS is primary for gamma because its live one-minute chain carries OI, IV,
  gamma and timestamps. Tradier remains source of truth for underlying/index spot.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import logging
from collections import defaultdict
from datetime import datetime, time as dtime
from typing import Any
from zoneinfo import ZoneInfo

import requests
from fastapi import APIRouter
from sqlalchemy import text

from .db import engine

logger = logging.getLogger(__name__)
CT = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")

router = APIRouter(prefix="/api/spreadworks/market-structure",
                   tags=["Market Structure"])

ORATS_URL = "https://api.orats.io/datav2/live/one-minute/strikes/chain"
TRADIER_QUOTES = "https://api.tradier.com/v1/markets/quotes"
SYMBOLS = ("SPY", "QQQ", "IWM", "XSP")
BUCKETS = ((0, 0, "0dte"), (1, 5, "1_5dte"), (6, 20, "6_20dte"),
           (21, 365, "21_365dte"))
STALE_SECONDS = int(os.getenv("MARKET_STRUCTURE_STALE_SECONDS", "90"))
GAMMA_TABLE = "sw_live_gamma"
VOL_TABLE = "sw_live_vol_indices"

_GAMMA_DDL = f"""
CREATE TABLE IF NOT EXISTS {GAMMA_TABLE} (
  symbol TEXT NOT NULL,
  captured_at TIMESTAMP NOT NULL,
  trade_date DATE NOT NULL,
  spot DOUBLE PRECISION,
  source TEXT NOT NULL,
  source_timestamp TIMESTAMP,
  confidence TEXT NOT NULL,
  n_rows INTEGER,
  net_gex_b DOUBLE PRECISION,
  gamma_flip DOUBLE PRECISION,
  call_wall DOUBLE PRECISION,
  put_wall DOUBLE PRECISION,
  bucket_json TEXT,
  wall_json TEXT,
  reason TEXT,
  PRIMARY KEY(symbol, captured_at)
)
"""

_VOL_DDL = f"""
CREATE TABLE IF NOT EXISTS {VOL_TABLE} (
  symbol TEXT NOT NULL,
  captured_at TIMESTAMP NOT NULL,
  price DOUBLE PRECISION,
  source TEXT NOT NULL,
  source_timestamp TIMESTAMP,
  age_seconds DOUBLE PRECISION,
  fresh BOOLEAN NOT NULL,
  reason TEXT,
  PRIMARY KEY(symbol, captured_at)
)
"""


def ensure_tables() -> None:
    with engine.begin() as conn:
        conn.execute(text(_GAMMA_DDL))
        conn.execute(text(_VOL_DDL))


def _token(name: str) -> str:
    return os.getenv(name, "").strip()


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    s = str(value).strip().replace(" T ", "T").replace(" Z", "Z")
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _quote_timestamp(q: dict[str, Any]) -> datetime | None:
    # Tradier timestamps are epoch-ms when present.
    for key in ("trade_date", "bid_date", "ask_date"):
        raw = q.get(key)
        if raw:
            try:
                return datetime.fromtimestamp(float(raw) / 1000.0, UTC)
            except (TypeError, ValueError, OSError):
                continue
    return None


def fetch_vol_indices(now: datetime | None = None) -> dict[str, Any]:
    """Fetch VIX/VIX9D/VIX3M/VVIX from Tradier and enforce quote freshness.

    No public-web fallback is allowed: missing means MISSING, stale means STALE.
    Symbol aliases can be overridden without code via VOL_INDEX_SYMBOL_MAP JSON,
    e.g. {"VIX9D":"$VIX9D"}.
    """
    now = now or datetime.now(UTC)
    token = _token("TRADIER_TOKEN") or _token("TRADIER_API_KEY")
    if not token:
        return {"available": False, "reason": "TRADIER_TOKEN missing", "indices": {}}

    mapping = {"VIX": "VIX", "VIX9D": "VIX9D", "VIX3M": "VIX3M", "VVIX": "VVIX"}
    raw_map = os.getenv("VOL_INDEX_SYMBOL_MAP", "").strip()
    if raw_map:
        try:
            mapping.update(json.loads(raw_map))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[MarketStructure] bad VOL_INDEX_SYMBOL_MAP: %r", exc)

    symbols = ",".join(dict.fromkeys(mapping.values()))
    try:
        r = requests.get(TRADIER_QUOTES,
                         params={"symbols": symbols},
                         headers={"Authorization": f"Bearer {token}",
                                  "Accept": "application/json"},
                         timeout=15)
        r.raise_for_status()
        rows = (r.json().get("quotes") or {}).get("quote") or []
        if isinstance(rows, dict):
            rows = [rows]
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"Tradier quote failure: {type(exc).__name__}",
                "indices": {}}

    by_symbol = {str(q.get("symbol", "")).upper(): q for q in rows}
    out: dict[str, Any] = {}
    for canonical, vendor_symbol in mapping.items():
        q = by_symbol.get(str(vendor_symbol).upper())
        if not q or q.get("last") is None:
            out[canonical] = {"symbol": canonical, "vendor_symbol": vendor_symbol,
                              "price": None, "fresh": False, "reason": "missing_quote"}
            continue
        stamp = _quote_timestamp(q)
        age = (now - stamp).total_seconds() if stamp else None
        fresh = age is not None and age <= STALE_SECONDS
        out[canonical] = {
            "symbol": canonical,
            "vendor_symbol": vendor_symbol,
            "price": float(q["last"]),
            "source_timestamp": stamp.isoformat() if stamp else None,
            "age_seconds": round(age, 1) if age is not None else None,
            "fresh": fresh,
            "reason": None if fresh else ("missing_timestamp" if stamp is None else "stale_quote"),
        }
    return {"available": any(v.get("fresh") for v in out.values()),
            "source": "Tradier production consolidated feed",
            "retrieved_at": now.isoformat(), "indices": out}


def fetch_spot(symbol: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    token = _token("TRADIER_TOKEN") or _token("TRADIER_API_KEY")
    if not token:
        return {"price": None, "fresh": False, "reason": "TRADIER_TOKEN missing"}
    try:
        r = requests.get(TRADIER_QUOTES, params={"symbols": symbol},
                         headers={"Authorization": f"Bearer {token}",
                                  "Accept": "application/json"}, timeout=15)
        r.raise_for_status()
        q = (r.json().get("quotes") or {}).get("quote") or {}
        if isinstance(q, list):
            q = q[0] if q else {}
        if q.get("last") is None:
            return {"price": None, "fresh": False, "reason": "missing_quote"}
        stamp = _quote_timestamp(q)
        age = (now - stamp).total_seconds() if stamp else None
        fresh = age is not None and age <= STALE_SECONDS
        return {"price": float(q["last"]), "fresh": fresh,
                "source_timestamp": stamp, "age_seconds": age,
                "reason": None if fresh else ("missing_timestamp" if stamp is None else "stale_quote")}
    except Exception as exc:  # noqa: BLE001
        return {"price": None, "fresh": False,
                "reason": f"Tradier quote failure: {type(exc).__name__}"}


def fetch_orats_chain(symbol: str) -> dict[str, Any]:
    token = _token("ORATS_API_TOKEN") or _token("ORATS_TOKEN")
    if not token:
        return {"rows": [], "reason": "ORATS_API_TOKEN missing", "source_timestamp": None}
    try:
        r = requests.get(ORATS_URL, params={"token": token, "ticker": symbol},
                         timeout=30)
        r.raise_for_status()
        text_body = r.text.strip()
        if not text_body:
            return {"rows": [], "reason": "empty ORATS response", "source_timestamp": None}
        rows = list(csv.DictReader(io.StringIO(text_body)))
    except Exception as exc:  # noqa: BLE001
        return {"rows": [], "reason": f"ORATS failure: {type(exc).__name__}",
                "source_timestamp": None}

    stamps = [_parse_ts(r.get("updatedAt") or r.get("quoteDate") or r.get("snapShotDate"))
              for r in rows]
    stamps = [s for s in stamps if s is not None]
    return {"rows": rows, "reason": None,
            "source_timestamp": max(stamps) if stamps else None}


def _f(row: dict[str, Any], name: str) -> float | None:
    raw = row.get(name)
    if raw in (None, "", "null", "None"):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _row_gamma(row: dict[str, Any], spot: float, right: str) -> float | None:
    """Revalue gamma at hypothetical spot for flip solving using row IV."""
    strike = _f(row, "strike")
    dte = _f(row, "dte")
    iv = _f(row, "callMidIv" if right == "call" else "putMidIv")
    if iv is None or iv <= 0:
        iv = _f(row, "smvVol")
    rate = _f(row, "residualRate") or 0.0
    if not strike or strike <= 0 or dte is None or dte < 0 or not iv or iv <= 0 or spot <= 0:
        return None
    # ORATS dte is calendar days. On 0DTE, use a small non-zero time so gamma
    # remains finite; this is a context map, not an execution Greek.
    t = max(float(dte) / 365.0, 1.0 / (365.0 * 24.0))
    sig_sqrt = iv * math.sqrt(t)
    if sig_sqrt <= 0:
        return None
    d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * t) / sig_sqrt
    pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi)
    return pdf / (spot * sig_sqrt)


def _gex_for_row(row: dict[str, Any], spot: float, revalue: bool = False) -> tuple[float, float]:
    gamma_default = _f(row, "gamma")
    call_gamma = _row_gamma(row, spot, "call") if revalue else gamma_default
    put_gamma = _row_gamma(row, spot, "put") if revalue else gamma_default
    call_oi = _f(row, "callOpenInterest") or 0.0
    put_oi = _f(row, "putOpenInterest") or 0.0
    factor = 100.0 * spot * spot * 0.01
    return ((call_gamma or 0.0) * call_oi * factor,
            -(put_gamma or 0.0) * put_oi * factor)


def _bucket_name(dte: float) -> str | None:
    for lo, hi, name in BUCKETS:
        if lo <= dte <= hi:
            return name
    return None


def compute_gamma_map(rows: list[dict[str, Any]], spot: float) -> dict[str, Any]:
    """Compute net GEX, tenor buckets, strike walls and a re-solved gamma flip."""
    if not rows or not spot or spot <= 0:
        return {"net_gex_b": None, "reason": "no_usable_chain"}

    strike_call: dict[float, float] = defaultdict(float)
    strike_put: dict[float, float] = defaultdict(float)
    buckets: dict[str, float] = defaultdict(float)
    usable = 0

    for row in rows:
        strike = _f(row, "strike")
        dte = _f(row, "dte")
        gamma = _f(row, "gamma")
        if strike is None or dte is None or gamma is None or gamma <= 0 or dte > 365:
            continue
        cg, pg = _gex_for_row(row, spot, revalue=False)
        if cg == 0 and pg == 0:
            continue
        strike_call[strike] += cg
        strike_put[strike] += pg
        name = _bucket_name(dte)
        if name:
            buckets[name] += cg + pg
        usable += 1

    if not usable:
        return {"net_gex_b": None, "reason": "no_usable_gamma_rows"}

    total = sum(strike_call.values()) + sum(strike_put.values())
    call_above = [(s, v) for s, v in strike_call.items() if s >= spot]
    put_below = [(s, v) for s, v in strike_put.items() if s <= spot]
    call_wall = max(call_above, key=lambda x: x[1])[0] if call_above else None
    put_wall = min(put_below, key=lambda x: x[1])[0] if put_below else None

    # Re-solve across +/-8%. Adaptive step keeps SPY/QQQ granular and XSP useful.
    lo, hi = spot * 0.92, spot * 1.08
    step = max(0.10, round(spot * 0.00035, 2))
    grid = []
    s = lo
    while s <= hi + step / 2:
        g = 0.0
        for row in rows:
            dte = _f(row, "dte")
            if dte is None or dte > 365:
                continue
            cg, pg = _gex_for_row(row, s, revalue=True)
            g += cg + pg
        grid.append((s, g))
        s += step

    flip = None
    if grid:
        best = min(grid, key=lambda x: abs(x[1]))
        for a, b in zip(grid, grid[1:]):
            if a[1] == 0:
                flip = a[0]
                break
            if a[1] * b[1] < 0:
                denom = abs(a[1]) + abs(b[1])
                w = abs(a[1]) / denom if denom else 0.5
                flip = a[0] + (b[0] - a[0]) * w
                break
        if flip is None and abs(best[1]) < max(abs(total) * 0.03, 1e7):
            flip = best[0]

    walls = {
        "top_call": sorted(({"strike": s, "gex_b": v / 1e9}
                            for s, v in strike_call.items()), key=lambda x: x["gex_b"], reverse=True)[:5],
        "top_put": sorted(({"strike": s, "gex_b": v / 1e9}
                           for s, v in strike_put.items()), key=lambda x: x["gex_b"])[:5],
    }
    return {
        "net_gex_b": total / 1e9,
        "gamma_regime": "positive" if total > 0 else "negative" if total < 0 else "flat",
        "gamma_flip": round(flip, 2) if flip is not None else None,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "buckets": {k: v / 1e9 for k, v in buckets.items()},
        "walls": walls,
        "n_rows": usable,
        "reason": None,
    }


def _confidence(chain_ts: datetime | None, now: datetime, n_rows: int,
                spot_fresh: bool) -> tuple[str, float | None, str | None]:
    age = (now - chain_ts).total_seconds() if chain_ts else None
    if not spot_fresh:
        return "LOW", age, "stale_or_missing_spot"
    if chain_ts is None:
        return "LOW", None, "missing_chain_timestamp"
    if age <= 30 and n_rows >= 100:
        return "HIGH", age, None
    if age <= STALE_SECONDS and n_rows >= 50:
        return "MEDIUM", age, None
    return "LOW", age, "stale_or_thin_chain"


def build_gamma_snapshot(symbol: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    symbol = symbol.upper()
    spot = fetch_spot(symbol, now)
    if not spot.get("fresh"):
        return {"symbol": symbol, "available": False, "confidence": "LOW",
                "reason": spot.get("reason"), "captured_at": now.isoformat()}
    chain = fetch_orats_chain(symbol)
    if not chain.get("rows"):
        return {"symbol": symbol, "available": False, "confidence": "LOW",
                "reason": chain.get("reason"), "captured_at": now.isoformat(),
                "spot": spot.get("price")}
    calc = compute_gamma_map(chain["rows"], float(spot["price"]))
    conf, chain_age, conf_reason = _confidence(chain.get("source_timestamp"), now,
                                                int(calc.get("n_rows") or 0), True)
    available = calc.get("net_gex_b") is not None and conf != "LOW"
    return {
        "symbol": symbol,
        "available": available,
        "captured_at": now.isoformat(),
        "spot": float(spot["price"]),
        "spot_age_seconds": round(float(spot["age_seconds"]), 1),
        "chain_timestamp": (chain["source_timestamp"].isoformat()
                            if chain.get("source_timestamp") else None),
        "chain_age_seconds": round(chain_age, 1) if chain_age is not None else None,
        "source": "ORATS live one-minute chain + Tradier spot",
        "confidence": conf,
        "reason": calc.get("reason") or conf_reason,
        **{k: v for k, v in calc.items() if k != "reason"},
    }


def persist_snapshot(snapshot: dict[str, Any]) -> None:
    if snapshot.get("net_gex_b") is None:
        return
    ensure_tables()
    captured = datetime.fromisoformat(snapshot["captured_at"].replace("Z", "+00:00"))
    chain_ts = (_parse_ts(snapshot.get("chain_timestamp"))
                if snapshot.get("chain_timestamp") else None)
    params = {
        "symbol": snapshot["symbol"], "captured": captured.replace(tzinfo=None),
        "date": captured.astimezone(CT).date(), "spot": snapshot.get("spot"),
        "source": snapshot.get("source") or "unknown",
        "source_ts": chain_ts.replace(tzinfo=None) if chain_ts else None,
        "confidence": snapshot.get("confidence") or "LOW",
        "n": snapshot.get("n_rows"), "g": snapshot.get("net_gex_b"),
        "flip": snapshot.get("gamma_flip"), "cw": snapshot.get("call_wall"),
        "pw": snapshot.get("put_wall"),
        "buckets": json.dumps(snapshot.get("buckets") or {}),
        "walls": json.dumps(snapshot.get("walls") or {}),
        "reason": snapshot.get("reason"),
    }
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO {GAMMA_TABLE} "
            "(symbol,captured_at,trade_date,spot,source,source_timestamp,confidence,"
            "n_rows,net_gex_b,gamma_flip,call_wall,put_wall,bucket_json,wall_json,reason) "
            "VALUES (:symbol,:captured,:date,:spot,:source,:source_ts,:confidence,"
            ":n,:g,:flip,:cw,:pw,:buckets,:walls,:reason) "
            "ON CONFLICT(symbol,captured_at) DO NOTHING"), params)


def persist_vol(vol: dict[str, Any], now: datetime | None = None) -> None:
    ensure_tables()
    now = now or datetime.now(UTC)
    with engine.begin() as conn:
        for symbol, item in (vol.get("indices") or {}).items():
            ts = _parse_ts(item.get("source_timestamp"))
            conn.execute(text(
                f"INSERT INTO {VOL_TABLE} "
                "(symbol,captured_at,price,source,source_timestamp,age_seconds,fresh,reason) "
                "VALUES (:s,:c,:p,:src,:st,:a,:f,:r) ON CONFLICT(symbol,captured_at) DO NOTHING"),
                {"s": symbol, "c": now.replace(tzinfo=None), "p": item.get("price"),
                 "src": vol.get("source") or "Tradier",
                 "st": ts.replace(tzinfo=None) if ts else None,
                 "a": item.get("age_seconds"), "f": bool(item.get("fresh")),
                 "r": item.get("reason")})


def capture_all() -> dict[str, Any]:
    now = datetime.now(UTC)
    now_ct = now.astimezone(CT)
    if now_ct.weekday() >= 5 or not (dtime(8, 30) <= now_ct.time() <= dtime(15, 5)):
        return {"captured": False, "reason": "market_closed", "captured_at": now.isoformat()}
    vol = fetch_vol_indices(now)
    persist_vol(vol, now)
    gamma = {}
    for symbol in SYMBOLS:
        snap = build_gamma_snapshot(symbol, now)
        gamma[symbol] = snap
        persist_snapshot(snap)
    return {"captured": True, "captured_at": now.isoformat(), "volatility": vol,
            "gamma": gamma}


def _latest_gamma(symbol: str) -> dict[str, Any] | None:
    ensure_tables()
    with engine.begin() as conn:
        row = conn.execute(text(
            f"SELECT captured_at,spot,source,source_timestamp,confidence,n_rows,"
            "net_gex_b,gamma_flip,call_wall,put_wall,bucket_json,wall_json,reason "
            f"FROM {GAMMA_TABLE} WHERE symbol=:s ORDER BY captured_at DESC LIMIT 1"),
            {"s": symbol}).fetchone()
    if not row:
        return None
    keys = ("captured_at","spot","source","source_timestamp","confidence","n_rows",
            "net_gex_b","gamma_flip","call_wall","put_wall","bucket_json","wall_json","reason")
    d = dict(zip(keys, row))
    for k in ("captured_at", "source_timestamp"):
        if d[k] is not None:
            d[k] = d[k].isoformat()
    d["buckets"] = json.loads(d.pop("bucket_json") or "{}")
    d["walls"] = json.loads(d.pop("wall_json") or "{}")
    return d


@router.get("/live")
def live_market_structure():
    """Fresh report payload. It NEVER silently substitutes old public data."""
    now = datetime.now(UTC)
    vol = fetch_vol_indices(now)
    gamma = {s: build_gamma_snapshot(s, now) for s in SYMBOLS}
    return {"captured_at": now.isoformat(), "freshness_limit_seconds": STALE_SECONDS,
            "volatility": vol, "gamma": gamma,
            "dealer_position_note": "Estimated from public OI/Greeks; dealer inventory is not directly observable.",
            "squeeze_note": "Intraday context only; existing 15:05 CT SQUEEZE close signal is unchanged."}


@router.get("/vol-indices")
def vol_indices():
    return fetch_vol_indices(datetime.now(UTC))


@router.get("/gamma/{symbol}")
def gamma_symbol(symbol: str):
    symbol = symbol.upper()
    if symbol not in SYMBOLS:
        return {"available": False, "reason": f"unsupported symbol {symbol}",
                "supported": SYMBOLS}
    return build_gamma_snapshot(symbol, datetime.now(UTC))


@router.get("/latest/{symbol}")
def latest_symbol(symbol: str):
    symbol = symbol.upper()
    if symbol not in SYMBOLS:
        return {"available": False, "reason": f"unsupported symbol {symbol}",
                "supported": SYMBOLS}
    row = _latest_gamma(symbol)
    return {"available": row is not None, "symbol": symbol, "snapshot": row}
