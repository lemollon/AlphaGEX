"""Live volatility-index + dealer-gamma market-structure engine.

This module is intentionally separate from the backtested daily SQUEEZE signal.
It provides intraday CONTEXT using ThetaData option Greeks, open interest,
and index prices. Tradier remains the ETF spot source.

Key rules:
- Never mix providers inside one gamma snapshot.
- Never reuse stale quotes silently.
- Gamma is estimated dealer exposure, not observed dealer inventory.
- ThetaData Greeks and OI are joined by contract. Missing OI or stale Greeks
  fail closed; OI's morning publication time is reported separately.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
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

TRADIER_QUOTES = "https://api.tradier.com/v1/markets/quotes"
SYMBOLS = ("SPY", "QQQ", "IWM", "XSP", "SPX", "NDX", "RUT")
INDEX_SYMBOLS = frozenset(("XSP", "SPX", "NDX", "RUT"))
VOL_SYMBOLS = ("VIX", "VIX9D", "VIX3M", "VVIX")
ET = ZoneInfo("America/New_York")
BUCKETS = ((0, 0, "0dte"), (1, 5, "1_5dte"), (6, 20, "6_20dte"),
           (21, 365, "21_365dte"))
STALE_SECONDS = int(os.getenv("MARKET_STRUCTURE_STALE_SECONDS", "90"))
GAMMA_TABLE = "sw_live_gamma"
VOL_TABLE = "sw_live_vol_indices"
_OI_CACHE: dict[str, tuple[datetime, datetime, dict[tuple[str, float, str], float]]] = {}

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


def _theta_ts(value: Any) -> datetime | None:
    """ThetaData v3 sends exchange-local naive timestamps (Eastern time)."""
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return (stamp.replace(tzinfo=ET) if stamp.tzinfo is None else stamp).astimezone(UTC)


def _theta_base() -> str:
    value = os.getenv("THETADATA_BASE_URL", "").strip().rstrip("/")
    return f"http://{value}" if value and "://" not in value else value


def _theta_rows(path: str, params: dict[str, Any], timeout: int = 35) -> list[dict[str, Any]]:
    base = _theta_base()
    if not base:
        raise RuntimeError("THETADATA_BASE_URL missing")
    response = requests.get(f"{base}{path}", params=params, timeout=timeout)
    response.raise_for_status()
    return list(csv.DictReader(io.StringIO(response.text))) if response.text.strip() else []


def _index_prices(symbols: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    rows = _theta_rows("/v3/index/snapshot/price", {"symbol": ",".join(symbols)})
    return {str(row.get("symbol", "")).upper(): row for row in rows}


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
    """Fetch the subscribed ThetaData index feed with exchange timestamps."""
    now = now or datetime.now(UTC)
    try:
        by_symbol = _index_prices(VOL_SYMBOLS)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"ThetaData index failure: {type(exc).__name__}",
                "indices": {}}
    out: dict[str, Any] = {}
    for symbol in VOL_SYMBOLS:
        row = by_symbol.get(symbol)
        price = _f(row, "price") if row else None
        if price is None:
            out[symbol] = {"symbol": symbol,
                              "price": None, "fresh": False, "reason": "missing_quote"}
            continue
        stamp = _theta_ts(row.get("timestamp"))
        age = (now - stamp).total_seconds() if stamp else None
        fresh = age is not None and 0 <= age <= STALE_SECONDS
        out[symbol] = {
            "symbol": symbol,
            "price": price,
            "source_timestamp": stamp.isoformat() if stamp else None,
            "age_seconds": round(age, 1) if age is not None else None,
            "fresh": fresh,
            "reason": None if fresh else ("missing_timestamp" if stamp is None else "stale_quote"),
        }
    return {"available": any(v.get("fresh") for v in out.values()),
            "source": "ThetaData index snapshot price",
            "retrieved_at": now.isoformat(), "indices": out}


def fetch_spot(symbol: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    if symbol in INDEX_SYMBOLS:
        try:
            row = _index_prices((symbol,)).get(symbol)
            price = _f(row, "price") if row else None
            stamp = _theta_ts(row.get("timestamp")) if row else None
            age = (now - stamp).total_seconds() if stamp else None
            fresh = price is not None and age is not None and 0 <= age <= STALE_SECONDS
            return {"price": price, "fresh": fresh, "source_timestamp": stamp,
                    "age_seconds": age, "source": "ThetaData index snapshot price",
                    "reason": None if fresh else "stale_or_missing_index_price"}
        except Exception as exc:  # noqa: BLE001
            return {"price": None, "fresh": False,
                    "reason": f"ThetaData index failure: {type(exc).__name__}"}
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


def fetch_theta_chain(symbol: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    params = {"symbol": symbol, "expiration": "*", "max_dte": 365,
              "strike_range": 60}
    try:
        try:
            greeks = _theta_rows("/v3/option/snapshot/greeks/all", params)
            gamma_source = "ThetaData Pro Greeks"
        except requests.HTTPError:
            # ThetaData's all-Greeks route requires Pro. Standard exposes IV,
            # from which gamma can be calculated without another vendor.
            greeks = _theta_rows("/v3/option/snapshot/greeks/implied_volatility", params)
            gamma_source = "ThetaData Standard IV, locally calculated gamma"
        cached = _OI_CACHE.get(symbol)
        if cached and cached[0].astimezone(ET).date() == now.astimezone(ET).date() and (now - cached[0]).total_seconds() < 3600:
            oi_stamp, oi_by_contract = cached[1], cached[2]
        else:
            oi_rows = _theta_rows("/v3/option/snapshot/open_interest", params)
            oi_stamps = [_theta_ts(row.get("timestamp")) for row in oi_rows]
            oi_stamps = [stamp for stamp in oi_stamps if stamp]
            if not oi_stamps:
                return {"rows": [], "reason": "stale_or_missing_theta_open_interest",
                        "source_timestamp": None}
            oi_stamp = max(oi_stamps)
            oi_by_contract = {}
            for item in oi_rows:
                strike = _f(item, "strike")
                amount = _f(item, "open_interest")
                if strike is not None and amount is not None and amount >= 0:
                    oi_by_contract[(str(item.get("expiration")), strike,
                                    str(item.get("right", "")).lower())] = amount
            if oi_stamp.astimezone(ET).date() == now.astimezone(ET).date() and oi_by_contract:
                # Keep only the join key and OI number, not full CSV dicts.
                _OI_CACHE[symbol] = (now, oi_stamp, oi_by_contract)
    except Exception as exc:  # noqa: BLE001
        return {"rows": [], "reason": f"ThetaData chain failure: {type(exc).__name__}",
                "source_timestamp": None}
    if not greeks or not oi_by_contract:
        return {"rows": [], "reason": "missing_theta_greeks_or_open_interest",
                "source_timestamp": None}

    # OI is an OPRA morning publication. Require today's snapshot, while the
    # Greeks carry the intraminute freshness requirement.
    if oi_stamp.astimezone(ET).date() != now.astimezone(ET).date():
        return {"rows": [], "reason": "stale_or_missing_theta_open_interest",
                "source_timestamp": None}

    recent: list[tuple[dict[str, Any], datetime]] = []
    for item in greeks:
        stamp = _theta_ts(item.get("timestamp"))
        if stamp and 0 <= (now - stamp).total_seconds() <= STALE_SECONDS:
            recent.append((item, stamp))
    rows: list[dict[str, Any]] = []
    for item, stamp in recent:
        strike = _f(item, "strike")
        right = str(item.get("right", "")).lower()
        expiry = str(item.get("expiration", ""))
        iv = _f(item, "implied_vol")
        if strike is None or right not in ("call", "put"):
            continue
        oi = oi_by_contract.get((expiry, strike, right))
        if oi is None:
            continue
        try:
            dte = (datetime.fromisoformat(expiry).date() - now.astimezone(ET).date()).days
        except ValueError:
            continue
        if not 0 <= dte <= 365:
            continue
        expiration_at = datetime.combine(datetime.fromisoformat(expiry).date(),
                                         dtime(16, 0), ET)
        tte_years = max(3600.0, (expiration_at - now.astimezone(ET)).total_seconds()) / (365 * 86400)
        rate = float(os.getenv("MARKET_STRUCTURE_RISK_FREE_RATE", "0.05"))
        row = {"strike": strike, "dte": dte,
                     "callOpenInterest": oi if right == "call" else 0,
                     "putOpenInterest": oi if right == "put" else 0,
                     "callMidIv": iv if right == "call" else None,
                     "putMidIv": iv if right == "put" else None,
                     "residualRate": rate, "tte_years": tte_years,
                     "timestamp": stamp}
        gamma = _f(item, "gamma")
        if gamma is None:
            underlying = _f(item, "underlying_price")
            gamma = _row_gamma(row, underlying or 0, right)
        if gamma is None or gamma <= 0:
            continue
        row["gamma"] = gamma
        rows.append(row)
    if len(rows) < 50 or len(rows) < len(recent) * 0.7:
        return {"rows": [], "reason": "thin_or_unmatched_theta_chain",
                "source_timestamp": None, "matched_rows": len(rows),
                "recent_greeks_rows": len(recent)}
    return {"rows": rows, "reason": None,
            "source_timestamp": min(row["timestamp"] for row in rows),
            "oi_timestamp": oi_stamp, "matched_rows": len(rows),
            "recent_greeks_rows": len(recent), "gamma_source": gamma_source}


def _f(row: dict[str, Any], name: str) -> float | None:
    raw = row.get(name)
    if raw in (None, "", "null", "None"):
        return None
    try:
        value = float(raw)
        return value if math.isfinite(value) else None
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
    # Calendar DTE is used for the approximate flip revaluation. ThetaData's
    # own live gamma is used for net GEX at the observed spot.
    t = _f(row, "tte_years") or max(float(dte) / 365.0, 1.0 / (365.0 * 24.0))
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

    # Re-solve across +/-8% using a bounded coarse grid and local bisection.
    # Full-chain per-tick scanning would block the minute capture for indices.
    lo, hi = spot * 0.92, spot * 1.08
    def gamma_at(candidate: float) -> float:
        return sum(sum(_gex_for_row(row, candidate, revalue=True))
                   for row in rows if (_f(row, "dte") or 0) <= 365)

    flip = None
    iv_rows = [row for row in rows if (_f(row, "callMidIv") or _f(row, "putMidIv"))]
    if len(iv_rows) >= max(50, usable * 0.7):
        grid = [(lo + (hi - lo) * i / 60, 0.0) for i in range(61)]
        grid = [(price, gamma_at(price)) for price, _ in grid]
        for a, b in zip(grid, grid[1:]):
            if a[1] == 0:
                flip = a[0]
                break
            if a[1] * b[1] < 0:
                left, right = a, b
                for _ in range(8):
                    middle = ((left[0] + right[0]) / 2.0, gamma_at((left[0] + right[0]) / 2.0))
                    if left[1] * middle[1] <= 0:
                        right = middle
                    else:
                        left = middle
                flip = (left[0] + right[0]) / 2.0
                break

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
    if age is not None and 0 <= age <= 30 and n_rows >= 100:
        return "HIGH", age, None
    if age is not None and 0 <= age <= STALE_SECONDS and n_rows >= 50:
        return "MEDIUM", age, None
    return "LOW", age, "stale_or_thin_chain"


def build_gamma_snapshot(symbol: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    symbol = symbol.upper()
    spot = fetch_spot(symbol, now)
    if not spot.get("fresh"):
        return {"symbol": symbol, "available": False, "confidence": "LOW",
                "reason": spot.get("reason"), "captured_at": now.isoformat()}
    chain = fetch_theta_chain(symbol, now)
    completed_at = datetime.now(UTC)
    if not chain.get("rows"):
        return {"symbol": symbol, "available": False, "confidence": "LOW",
                "reason": chain.get("reason"), "captured_at": completed_at.isoformat(),
                "spot": spot.get("price")}
    calc = compute_gamma_map(chain["rows"], float(spot["price"]))
    completed_at = datetime.now(UTC)
    spot_stamp = spot.get("source_timestamp")
    spot_age = (completed_at - spot_stamp).total_seconds() if spot_stamp else None
    spot_fresh = spot_age is not None and 0 <= spot_age <= STALE_SECONDS
    conf, chain_age, conf_reason = _confidence(chain.get("source_timestamp"), completed_at,
                                                int(calc.get("n_rows") or 0), spot_fresh)
    available = calc.get("net_gex_b") is not None and conf != "LOW"
    return {
        "symbol": symbol,
        "available": available,
        "captured_at": completed_at.isoformat(),
        "spot": float(spot["price"]),
        "spot_age_seconds": round(spot_age, 1) if spot_age is not None else None,
        "chain_timestamp": (chain["source_timestamp"].isoformat()
                            if chain.get("source_timestamp") else None),
        "chain_age_seconds": round(chain_age, 1) if chain_age is not None else None,
        "source": f"{chain.get('gamma_source', 'ThetaData options')} + OPRA OI + {spot.get('source', 'Tradier ETF spot')}",
        "oi_timestamp": (chain["oi_timestamp"].isoformat()
                         if chain.get("oi_timestamp") else None),
        "oi_matched_rows": chain.get("matched_rows"),
        "recent_greeks_rows": chain.get("recent_greeks_rows"),
        "confidence": conf,
        "reason": calc.get("reason") or conf_reason,
        **{k: v for k, v in calc.items() if k != "reason"},
    }


def persist_snapshot(snapshot: dict[str, Any]) -> None:
    """Persist both usable gamma maps and failed/LOW-confidence attempts.

    Failure rows are intentional observability: downstream reports can tell the
    difference between "capture never ran" and "ThetaData/spot was unavailable".
    Numeric gamma fields remain NULL on failure and therefore cannot be treated
    as valid market structure.
    """
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
                 "src": vol.get("source") or "ThetaData",
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
    gamma: dict[str, Any] = {}
    # Fetch independent symbols concurrently; each ThetaData request retains
    # a bounded proxy timeout and each result must pass its freshness gate.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="market-structure") as pool:
        futures = {pool.submit(build_gamma_snapshot, symbol, now): symbol for symbol in SYMBOLS}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                snap = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.exception("[MarketStructure] %s gamma capture crashed", symbol)
                snap = {
                    "symbol": symbol,
                    "available": False,
                    "confidence": "LOW",
                    "reason": f"capture_exception:{type(exc).__name__}",
                    "captured_at": now.isoformat(),
                }
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


def register(scheduler: Any, app: Any | None = None) -> bool:
    """Persist canonical live market structure once a minute on market days.

    The /live route remains an on-demand view, but durable minute captures are
    required so downstream reports can recover through Render/Postgres when a
    client cannot reach the public onrender.com URL.
    """
    if scheduler is None:
        logger.error("[MarketStructure] scheduler unavailable; minute capture is not armed")
        return False

    ensure_tables()

    def tick() -> None:
        try:
            result = capture_all()
            if result.get("captured"):
                available = sum(
                    1 for item in (result.get("gamma") or {}).values()
                    if item.get("available")
                )
                logger.info(
                    "[MarketStructure] capture complete gamma_available=%d/%d vol_available=%s",
                    available, len(SYMBOLS),
                    bool((result.get("volatility") or {}).get("available")),
                )
        except Exception:  # noqa: BLE001
            logger.exception("[MarketStructure] minute capture failed")

    scheduler.add_job(
        tick, "cron", day_of_week="mon-fri", hour="8-15", minute="*",
        timezone=CT, id="market_structure_capture", replace_existing=True,
        coalesce=True, max_instances=1, misfire_grace_time=90,
        next_run_time=datetime.now(UTC),
    )
    logger.info(
        "[MarketStructure] registered minute captures 08:00-15:59 CT; "
        "capture_all enforces the 08:30-15:05 market window"
    )
    return True


@router.get("/live")
def live_market_structure():
    """Fresh report payload. It NEVER silently substitutes old public data."""
    now = datetime.now(UTC)
    vol = fetch_vol_indices(now)
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="theta-live") as pool:
        futures = {pool.submit(build_gamma_snapshot, s, now): s for s in SYMBOLS}
        gamma = {}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                gamma[symbol] = future.result()
            except Exception as exc:  # noqa: BLE001
                gamma[symbol] = {"symbol": symbol, "available": False,
                                 "confidence": "LOW",
                                 "reason": f"capture_exception:{type(exc).__name__}",
                                 "captured_at": now.isoformat()}
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
