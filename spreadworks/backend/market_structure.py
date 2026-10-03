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
import statistics
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as dtime, timedelta
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
TRADIER_TIMESALES = "https://api.tradier.com/v1/markets/timesales"
SYMBOLS = ("SPY", "QQQ", "IWM", "XSP", "SPX", "NDX", "RUT")
INDEX_SYMBOLS = frozenset(("XSP", "SPX", "NDX", "RUT"))
VOL_SYMBOLS = ("VIX", "VIX1D", "VIX9D", "VIX3M", "VVIX")
ET = ZoneInfo("America/New_York")
BUCKETS = ((0, 0, "0dte"), (1, 5, "1_5dte"), (6, 20, "6_20dte"),
           (21, 365, "21_365dte"))
STALE_SECONDS = int(os.getenv("MARKET_STRUCTURE_STALE_SECONDS", "90"))
GAMMA_TABLE = "sw_live_gamma"
VOL_TABLE = "sw_live_vol_indices"
SURFACE_TABLE = "sw_live_surface"
FLOW_TABLE = "sw_live_trade_quote_flow"
CROSS_ASSET_TABLE = "sw_live_cross_asset"
CROSS_ASSET_SYMBOLS = ("SPY", "QQQ", "IWM", "SMH", "XLK", "XLF", "XLE", "XLV", "XLU", "XLY", "XLP", "HYG", "LQD", "TLT")
# Gamma only needs the near-term, near-spot chain used by the intraday map.
# Keeping this bounded is critical: ThetaData serializes requests in the shared
# proxy, so an all-expiry/all-strike OI request can block surface refreshes for
# long enough to fail the report freshness gate.
GAMMA_MAX_DTE = int(os.getenv("MARKET_STRUCTURE_GAMMA_MAX_DTE", "60"))
GAMMA_STRIKE_RANGE = int(os.getenv("MARKET_STRUCTURE_GAMMA_STRIKE_RANGE", "25"))
_OI_CACHE: dict[tuple[str, int, int], tuple[datetime, datetime, dict[tuple[str, float, str], float]]] = {}

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

_SURFACE_DDL = f"""
CREATE TABLE IF NOT EXISTS {SURFACE_TABLE} (
  symbol TEXT NOT NULL,
  captured_at TIMESTAMP NOT NULL,
  trade_date DATE NOT NULL,
  spot DOUBLE PRECISION,
  source TEXT NOT NULL,
  source_timestamp TIMESTAMP,
  confidence TEXT NOT NULL,
  n_rows INTEGER,
  atm_iv DOUBLE PRECISION,
  atm_reference_dte INTEGER,
  skew_25d DOUBLE PRECISION,
  skew_reference_dte INTEGER,
  iv_0dte DOUBLE PRECISION,
  iv_1_5dte DOUBLE PRECISION,
  iv_6_20dte DOUBLE PRECISION,
  iv_21_365dte DOUBLE PRECISION,
  expected_move_pct_1d DOUBLE PRECISION,
  expected_move_dollars_1d DOUBLE PRECISION,
  expected_move_low DOUBLE PRECISION,
  expected_move_high DOUBLE PRECISION,
  realized_vol_60m DOUBLE PRECISION,
  realized_vol_bars INTEGER,
  realized_vol_source_timestamp TIMESTAMP,
  realized_vol_bar_timestamp TIMESTAMP,
  iv_minus_realized_vol DOUBLE PRECISION,
  reason TEXT,
  PRIMARY KEY(symbol, captured_at)
)
"""

_FLOW_DDL = f"""
CREATE TABLE IF NOT EXISTS {FLOW_TABLE} (
  symbol TEXT NOT NULL,
  captured_at TIMESTAMP NOT NULL,
  trade_date DATE NOT NULL,
  source TEXT NOT NULL,
  source_timestamp TIMESTAMP,
  confidence TEXT NOT NULL,
  n_trades INTEGER,
  bucket_json TEXT,
  reason TEXT,
  PRIMARY KEY(symbol, captured_at)
)
"""


_CROSS_ASSET_DDL = f"""
CREATE TABLE IF NOT EXISTS {CROSS_ASSET_TABLE} (
  symbol TEXT NOT NULL,
  captured_at TIMESTAMP NOT NULL,
  price DOUBLE PRECISION,
  open_price DOUBLE PRECISION,
  prev_close DOUBLE PRECISION,
  source_timestamp TIMESTAMP,
  fresh BOOLEAN NOT NULL,
  reason TEXT,
  PRIMARY KEY(symbol, captured_at)
)
"""


def ensure_tables() -> None:
    with engine.begin() as conn:
        conn.execute(text(_GAMMA_DDL))
        conn.execute(text(_VOL_DDL))
        conn.execute(text(_SURFACE_DDL))
        conn.execute(text(_FLOW_DDL))
        conn.execute(text(_CROSS_ASSET_DDL))
        # Existing deployments already have the original table.  Keep this
        # additive migration here so a rolling deploy cannot leave reports
        # without the realized-volatility fields.
        for column, sql_type in (
            ("realized_vol_60m", "DOUBLE PRECISION"),
            ("realized_vol_bars", "INTEGER"),
            ("realized_vol_source_timestamp", "TIMESTAMP"),
            ("realized_vol_bar_timestamp", "TIMESTAMP"),
            ("iv_minus_realized_vol", "DOUBLE PRECISION"),
            ("surface_json", "TEXT"),
        ):
            conn.execute(text(
                f"ALTER TABLE {SURFACE_TABLE} ADD COLUMN IF NOT EXISTS {column} {sql_type}"
            ))
        conn.execute(text(f"ALTER TABLE {FLOW_TABLE} ADD COLUMN IF NOT EXISTS evidence_json TEXT"))


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


def _theta_live_snapshot_rows(path: str, params: dict[str, Any], observed_at: datetime) -> list[dict[str, Any]]:
    """Read a live Theta snapshot and supply its receipt time only if needed.

    The authorized IV snapshot occasionally omits a per-contract timestamp.
    That does not make the data stale: the entire response is a point-in-time
    snapshot fetched synchronously.  Preserve a provider timestamp whenever it
    exists, but attach the observed exchange-local time for timestamp-less rows
    so the normal <=90-second guard can evaluate the actual snapshot age.
    """
    rows = _theta_rows(path, params)
    fallback_stamp = observed_at.astimezone(ET).replace(tzinfo=None).isoformat()
    for row in rows:
        if not str(row.get("timestamp") or "").strip():
            row["timestamp"] = fallback_stamp
    return rows


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
    """Fetch ThetaData indices, preserving a fresh Tradier VIX if it is denied."""
    now = now or datetime.now(UTC)
    try:
        by_symbol = _index_prices(VOL_SYMBOLS)
    except Exception as exc:  # noqa: BLE001
        reason = "ThetaData index permission denied" if (
            isinstance(exc, requests.HTTPError) and exc.response is not None
            and exc.response.status_code == 403
        ) else f"ThetaData index failure: {type(exc).__name__}"
        # The independent Tradier VIX quote is still useful for spot-vol
        # confirmation. Label it explicitly; do not substitute it for an
        # index spot in the ThetaData option-gamma calculation.
        token = _token("TRADIER_TOKEN") or _token("TRADIER_API_KEY")
        if token:
            try:
                response = requests.get(
                    TRADIER_QUOTES, params={"symbols": "VIX"},
                    headers={"Authorization": f"Bearer {token}",
                             "Accept": "application/json"}, timeout=15,
                )
                response.raise_for_status()
                quote = (response.json().get("quotes") or {}).get("quote") or {}
                if isinstance(quote, list):
                    quote = quote[0] if quote else {}
                stamp = _quote_timestamp(quote)
                price = _f(quote, "last")
                checked_at = datetime.now(UTC)
                age = (checked_at - stamp).total_seconds() if stamp else None
                if price is not None and age is not None and 0 <= age <= STALE_SECONDS:
                    return {
                        "available": True, "source": "Tradier VIX quote",
                        "provider_error": reason, "retrieved_at": checked_at.isoformat(),
                        "indices": {"VIX": {
                            "symbol": "VIX", "price": price,
                            "source_timestamp": stamp.isoformat(),
                            "age_seconds": round(age, 1), "fresh": True,
                            "reason": None,
                        }},
                    }
            except Exception as fallback_exc:  # noqa: BLE001
                logger.warning("[MarketStructure] Tradier VIX fallback failed: %s",
                               type(fallback_exc).__name__)
        return {"available": False, "reason": reason, "indices": {}}
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


def fetch_cross_asset(now: datetime | None = None) -> dict[str, Any]:
    """Fresh sector/credit dashboard from one Tradier batch quote request."""
    now = now or datetime.now(UTC)
    token = _token("TRADIER_TOKEN") or _token("TRADIER_API_KEY")
    if not token:
        return {"available": False, "reason": "TRADIER_TOKEN missing", "assets": {}}
    try:
        response = requests.get(
            TRADIER_QUOTES, params={"symbols": ",".join(CROSS_ASSET_SYMBOLS)},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        # Quote timestamps can be a few milliseconds after the request began.
        # Freshness must be measured against the completed response, not its
        # pre-request clock, otherwise valid quotes are falsely rejected.
        observed_at = datetime.now(UTC)
        raw = (response.json().get("quotes") or {}).get("quote") or []
        if isinstance(raw, dict):
            raw = [raw]
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"Tradier cross-asset failure: {type(exc).__name__}",
                "assets": {}}

    assets: dict[str, Any] = {}
    for quote in raw:
        symbol = str(quote.get("symbol") or "").upper()
        if symbol not in CROSS_ASSET_SYMBOLS:
            continue
        price = _f(quote, "last")
        stamp = _quote_timestamp(quote)
        age = (observed_at - stamp).total_seconds() if stamp else None
        fresh = price is not None and age is not None and 0 <= age <= STALE_SECONDS
        assets[symbol] = {
            "symbol": symbol, "price": price, "open_price": _f(quote, "open"),
            "prev_close": _f(quote, "prevclose"), "source_timestamp": stamp,
            "age_seconds": round(age, 1) if age is not None else None, "fresh": fresh,
            "reason": None if fresh else "stale_or_missing_quote",
        }
    return {"available": all(assets.get(symbol, {}).get("fresh")
                             for symbol in CROSS_ASSET_SYMBOLS),
            "source": "Tradier batch ETF quotes", "retrieved_at": observed_at.isoformat(),
            "assets": assets}


def persist_cross_asset(payload: dict[str, Any], now: datetime | None = None) -> None:
    ensure_tables()
    now = now or datetime.now(UTC)
    with engine.begin() as conn:
        for symbol in CROSS_ASSET_SYMBOLS:
            item = (payload.get("assets") or {}).get(symbol) or {"symbol": symbol}
            stamp = item.get("source_timestamp")
            conn.execute(text(
                f"INSERT INTO {CROSS_ASSET_TABLE} "
                "(symbol,captured_at,price,open_price,prev_close,source_timestamp,fresh,reason) "
                "VALUES (:symbol,:captured,:price,:open,:prev,:stamp,:fresh,:reason) "
                "ON CONFLICT(symbol,captured_at) DO NOTHING"),
                {"symbol": symbol, "captured": now.replace(tzinfo=None),
                 "price": item.get("price"), "open": item.get("open_price"),
                 "prev": item.get("prev_close"),
                 "stamp": stamp.replace(tzinfo=None) if stamp else None,
                 "fresh": bool(item.get("fresh")), "reason": item.get("reason")})


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
            reason = "ThetaData index permission denied" if (
                isinstance(exc, requests.HTTPError) and exc.response is not None
                and exc.response.status_code == 403
            ) else f"ThetaData index failure: {type(exc).__name__}"
            return {"price": None, "fresh": False,
                    "reason": reason}
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


def fetch_theta_chain(symbol: str, now: datetime | None = None,
                      max_dte: int | None = None,
                      strike_range: int | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    max_dte = max_dte if max_dte is not None else GAMMA_MAX_DTE
    strike_range = strike_range if strike_range is not None else GAMMA_STRIKE_RANGE
    params = {"symbol": symbol, "expiration": "*", "max_dte": max_dte,
              "strike_range": strike_range}
    cache_key = (symbol, max_dte, strike_range)
    try:
        try:
            greeks = _theta_live_snapshot_rows(
                "/v3/option/snapshot/greeks/all", params, now
            )
            gamma_source = "ThetaData Pro Greeks"
        except requests.HTTPError:
            # ThetaData's all-Greeks route requires Pro. Standard exposes IV,
            # from which gamma can be calculated without another vendor.
            greeks = _theta_live_snapshot_rows(
                "/v3/option/snapshot/greeks/implied_volatility", params, now
            )
            gamma_source = "ThetaData Standard IV, locally calculated gamma"
        cached = _OI_CACHE.get(cache_key)
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
                _OI_CACHE[cache_key] = (now, oi_stamp, oi_by_contract)
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
                     "timestamp": stamp,
                     "underlying_price": _f(item, "underlying_price")}
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


def _iv(raw: Any) -> float | None:
    """Normalize ThetaData IV to a decimal without accepting implausible data."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    # ThetaData normally returns 0.18, but accept a percent-form response too.
    if 3 < value <= 300:
        value /= 100.0
    return value if 0 < value <= 3 else None


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _option_delta(spot: float, strike: float, iv: float, dte: int, right: str) -> float | None:
    """Black-Scholes delta used only to locate the 25-delta IV points.

    This is deliberately not presented as a vendor Greek.  It lets the
    authorized IV-only feed supply a stable skew measure when the optional
    ThetaData all-Greeks entitlement is not present.
    """
    if min(spot, strike, iv) <= 0 or right not in {"call", "put"}:
        return None
    t = max(float(max(dte, 1)) / 365.0, 1.0 / (365.0 * 24.0))
    sigma_t = iv * math.sqrt(t)
    if sigma_t <= 0:
        return None
    rate = float(os.getenv("MARKET_STRUCTURE_RISK_FREE_RATE", "0.05"))
    d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * t) / sigma_t
    call_delta = _normal_cdf(d1)
    return call_delta if right == "call" else call_delta - 1.0


def _surface_rows(symbol: str, now: datetime, *, background: bool = False) -> tuple[list[dict[str, Any]], str | None]:
    """Read the ThetaData endpoint that is included with the current plan.

    Do not route this through the all-Greeks endpoint.  That add-on is denied
    on the deployed account, while the IV snapshot endpoint is explicitly
    authorized and is sufficient for ATM IV, term structure, skew and an
    IV-based one-day expected move.
    """
    params = {"symbol": symbol, "expiration": "*", "max_dte": 365,
              "strike_range": 60}
    if background:
        params["background"] = "true"
    # Receipt time does not refresh the option's NBBO or its underlying.
    # Require the provider clocks; otherwise this could relabel yesterday's IV live.
    # Retry one thin response immediately; this removes a transient provider
    # sampling gap without loosening the live-snapshot requirement.
    for attempt in range(1 if background else 2):
        try:
            raw_rows = _theta_rows("/v3/option/snapshot/greeks/implied_volatility", params)
        except Exception as exc:  # noqa: BLE001
            if background or (isinstance(…8636 tokens truncated…n
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


def _spot_from_theta_chain(chain: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    """Recover an index spot only from consistent, fresh Theta option rows."""
    priced = [(row["underlying_price"], row["timestamp"])
              for row in chain.get("rows") or []
              if _f(row, "underlying_price") is not None
              and _f(row, "underlying_price") > 0]
    if len(priced) < 50:
        return None
    prices = [price for price, _ in priced]
    middle = statistics.median(prices)
    if max(prices) - min(prices) > middle * 0.01:
        return None
    stamp = min(ts for _, ts in priced)
    age = (now - stamp).total_seconds()
    if not 0 <= age <= STALE_SECONDS:
        return None
    return {"price": middle, "fresh": True, "source_timestamp": stamp,
            "age_seconds": age, "source": "ThetaData option-chain underlying price"}


def build_gamma_snapshot(symbol: str, now: datetime | None = None,
                         max_dte: int | None = None,
                         strike_range: int | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    symbol = symbol.upper()
    spot = fetch_spot(symbol, now)
    chain = None

    def load_chain() -> dict[str, Any]:
        if max_dte is None and strike_range is None:
            return fetch_theta_chain(symbol, now)
        return fetch_theta_chain(symbol, now, max_dte=max_dte,
                                 strike_range=strike_range)

    if symbol in INDEX_SYMBOLS and not spot.get("fresh"):
        chain = load_chain()
        chain_spot = _spot_from_theta_chain(chain, datetime.now(UTC))
        if chain_spot:
            spot = chain_spot
    if not spot.get("fresh"):
        return {"symbol": symbol, "available": False, "confidence": "LOW",
                "reason": (chain or {}).get("reason") or spot.get("reason"),
                "captured_at": datetime.now(UTC).isoformat()}
    chain = chain if chain is not None else load_chain()
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
        "spot_source": spot.get("source") or "Tradier ETF quote",
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


def persist_surface(surface: dict[str, Any]) -> None:
    """Persist a surface attempt every minute, including a failed attempt.

    The row is an operational contract for reports: absence means the writer
    did not run; LOW confidence means it ran but did not pass the live gate.
    """
    ensure_tables()
    captured = datetime.fromisoformat(surface["captured_at"].replace("Z", "+00:00"))
    source_ts = _parse_ts(surface.get("source_timestamp")) if surface.get("source_timestamp") else None
    realized_source_ts = (_parse_ts(surface.get("realized_vol_source_timestamp"))
                          if surface.get("realized_vol_source_timestamp") else None)
    realized_bar_ts = (_parse_ts(surface.get("realized_vol_bar_timestamp"))
                       if surface.get("realized_vol_bar_timestamp") else None)
    params = {
        "symbol": surface["symbol"], "captured": captured.replace(tzinfo=None),
        "date": captured.astimezone(CT).date(), "spot": surface.get("spot"),
        "source": surface.get("source") or "ThetaData implied-volatility snapshots",
        "source_ts": source_ts.replace(tzinfo=None) if source_ts else None,
        "confidence": surface.get("confidence") or "LOW", "n": surface.get("n_rows"),
        "atm": surface.get("atm_iv"), "atm_dte": surface.get("atm_reference_dte"),
        "skew": surface.get("skew_25d"), "skew_dte": surface.get("skew_reference_dte"),
        "iv0": surface.get("iv_0dte"), "iv15": surface.get("iv_1_5dte"),
        "iv620": surface.get("iv_6_20dte"), "iv21": surface.get("iv_21_365dte"),
        "emp": surface.get("expected_move_pct_1d"),
        "emd": surface.get("expected_move_dollars_1d"),
        "emlow": surface.get("expected_move_low"), "emhigh": surface.get("expected_move_high"),
        "rv": surface.get("realized_vol_60m"),
        "rv_bars": surface.get("realized_vol_bars"),
        "rv_source_ts": realized_source_ts.replace(tzinfo=None) if realized_source_ts else None,
        "rv_bar_ts": realized_bar_ts.replace(tzinfo=None) if realized_bar_ts else None,
        "iv_minus_rv": surface.get("iv_minus_realized_vol"),
        "reason": surface.get("reason"),
        "surface_json": json.dumps({key: surface.get(key) for key in
                                    ("smile", "surface_points", "surface_read", "expected_move_method")}),
    }
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO {SURFACE_TABLE} "
            "(symbol,captured_at,trade_date,spot,source,source_timestamp,confidence,n_rows,"
            "atm_iv,atm_reference_dte,skew_25d,skew_reference_dte,iv_0dte,iv_1_5dte,"
            "iv_6_20dte,iv_21_365dte,expected_move_pct_1d,expected_move_dollars_1d,"
            "expected_move_low,expected_move_high,realized_vol_60m,realized_vol_bars,"
            "realized_vol_source_timestamp,realized_vol_bar_timestamp,iv_minus_realized_vol,reason,surface_json) "
            "VALUES (:symbol,:captured,:date,:spot,:source,:source_ts,:confidence,:n,"
            ":atm,:atm_dte,:skew,:skew_dte,:iv0,:iv15,:iv620,:iv21,:emp,:emd,:emlow,:emhigh,"
            ":rv,:rv_bars,:rv_source_ts,:rv_bar_ts,:iv_minus_rv,:reason,:surface_json) "
            "ON CONFLICT(symbol,captured_at) DO NOTHING"), params)


def persist_trade_quote_flow(flow: dict[str, Any]) -> None:
    """Persist every flow attempt so reports can use a dated fallback safely."""
    ensure_tables()
    captured = datetime.fromisoformat(flow["captured_at"].replace("Z", "+00:00"))
    source_ts = _parse_ts(flow.get("source_timestamp")) if flow.get("source_timestamp") else None
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO {FLOW_TABLE} "
            "(symbol,captured_at,trade_date,source,source_timestamp,confidence,n_trades,bucket_json,reason,evidence_json) "
            "VALUES (:symbol,:captured,:date,:source,:source_ts,:confidence,:n,:buckets,:reason,:evidence) "
            "ON CONFLICT(symbol,captured_at) DO NOTHING"),
            {"symbol": flow["symbol"], "captured": captured.replace(tzinfo=None),
             "date": captured.astimezone(CT).date(),
             "source": flow.get("source") or "ThetaData OPRA trade + NBBO",
             "source_ts": source_ts.replace(tzinfo=None) if source_ts else None,
             "confidence": flow.get("confidence") or "LOW", "n": flow.get("n_trades"),
             "buckets": json.dumps(flow.get("buckets") or {}), "reason": flow.get("reason"),
             "evidence": json.dumps(flow.get("evidence") or {})})


def capture_all() -> dict[str, Any]:
    now = datetime.now(UTC)
    now_ct = now.astimezone(CT)
    if now_ct.weekday() >= 5 or not (dtime(8, 30) <= now_ct.time() <= dtime(15, 5)):
        return {"captured": False, "reason": "market_closed", "captured_at": now.isoformat()}
    vol = fetch_vol_indices(now)
    persist_vol(vol, now)
    # Independent batch quotes cannot be starved by the serialized Theta client.
    cross_asset = fetch_cross_asset(now)
    persist_cross_asset(cross_asset, now)
    surface: dict[str, Any] = {}
    # Surface is intentionally limited to the two report underlyings.  It uses
    # the entitled IV-only endpoint and does not depend on the optional Greeks
    # package or the slower OI join used by the dealer-gamma map.  Capture it
    # first: a full seven-index gamma pass can take longer than the 90-second
    # freshness contract and must never starve the report's live IV fields.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="iv-surface") as pool:
        futures = {pool.submit(build_volatility_surface, symbol, datetime.now(UTC)): symbol
                   for symbol in ("SPY", "QQQ")}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                item = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.exception("[MarketStructure] %s IV surface capture crashed", symbol)
                item = {"symbol": symbol, "available": False, "confidence": "LOW",
                        "reason": f"capture_exception:{type(exc).__name__}",
                        "captured_at": datetime.now(UTC).isoformat()}
            surface[symbol] = item
            persist_surface(item)
    # Do not queue slow chain or historical-print requests behind the minute
    # surface capture. They can consume the single Theta client for tens of
    # seconds and used to turn an otherwise valid surface into a stale report.
    # Gamma/flow are fetched by their own explicit workers and read from their
    # persisted snapshots below; the report path never recalculates them.
    return {"captured": True, "captured_at": now.isoformat(), "volatility": vol,
            "cross_asset": cross_asset, "surface": surface}


def capture_gamma_pair() -> dict[str, Any]:
    """Persist a bounded, report-grade SPY/QQQ gamma map without blocking IV."""
    now = datetime.now(UTC)
    now_ct = now.astimezone(CT)
    if now_ct.weekday() >= 5 or not (dtime(8, 30) <= now_ct.time() <= dtime(15, 5)):
        return {"captured": False, "reason": "market_closed", "captured_at": now.isoformat()}

    snapshots: dict[str, Any] = {}
    # Sequential by design: concurrent submissions only queue at the proxy's
    # single Theta client and make timeout ordering nondeterministic.
    for symbol in ("SPY", "QQQ"):
        try:
            snapshot = build_gamma_snapshot(
                symbol, datetime.now(UTC), max_dte=GAMMA_MAX_DTE,
                strike_range=GAMMA_STRIKE_RANGE,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[MarketStructure] %s gamma capture crashed", symbol)
            snapshot = {"symbol": symbol, "available": False, "confidence": "LOW",
                        "reason": f"capture_exception:{type(exc).__name__}",
                        "captured_at": datetime.now(UTC).isoformat()}
        persist_snapshot(snapshot)
        snapshots[symbol] = snapshot
    return {"captured": True, "captured_at": now.isoformat(), "gamma": snapshots}


def recover_critical_surface() -> dict[str, Any]:
    """Self-heal a stale/missing report surface without waiting for the next tick."""
    now = datetime.now(UTC)
    now_ct = now.astimezone(CT)
    if now_ct.weekday() >= 5 or not (dtime(8, 30) <= now_ct.time() <= dtime(15, 5)):
        return {"recovered": False, "reason": "market_closed"}
    recovered: dict[str, Any] = {}
    for symbol in ("SPY", "QQQ"):
        cached = _cached_surface_payload(symbol, now)
        if cached.get("available"):
            recovered[symbol] = cached
            continue
        item = build_volatility_surface(symbol, datetime.now(UTC))
        persist_surface(item)
        recovered[symbol] = item
    return {"recovered": all(item.get("available") for item in recovered.values()),
            "captured_at": datetime.now(UTC).isoformat(), "surface": recovered}


def _latest_gamma(symbol: str, *, verified_only: bool = False) -> dict[str, Any] | None:
    ensure_tables()
    with engine.begin() as conn:
        row = conn.execute(text(
            f"SELECT captured_at,spot,source,source_timestamp,confidence,n_rows,"
            "net_gex_b,gamma_flip,call_wall,put_wall,bucket_json,wall_json,reason "
            f"FROM {GAMMA_TABLE} WHERE symbol=:s "
            + ("AND confidence IN ('HIGH','MEDIUM') AND net_gex_b IS NOT NULL " if verified_only else "")
            + "ORDER BY captured_at DESC LIMIT 1"),
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


def _latest_surface(symbol: str, *, verified_only: bool = False) -> dict[str, Any] | None:
    ensure_tables()
    with engine.begin() as conn:
        row = conn.execute(text(
            f"SELECT captured_at,spot,source,source_timestamp,confidence,n_rows,atm_iv,"
            "atm_reference_dte,skew_25d,skew_reference_dte,iv_0dte,iv_1_5dte,"
            "iv_6_20dte,iv_21_365dte,expected_move_pct_1d,expected_move_dollars_1d,"
            "expected_move_low,expected_move_high,realized_vol_60m,realized_vol_bars,"
            "realized_vol_source_timestamp,realized_vol_bar_timestamp,iv_minus_realized_vol,reason,surface_json "
            f"FROM {SURFACE_TABLE} WHERE symbol=:s "
            + ("AND confidence IN ('HIGH','MEDIUM') AND atm_iv IS NOT NULL " if verified_only else "")
            + "ORDER BY captured_at DESC LIMIT 1"),
            {"s": symbol}).fetchone()
    if not row:
        return None
    keys = ("captured_at","spot","source","source_timestamp","confidence","n_rows","atm_iv",
            "atm_reference_dte","skew_25d","skew_reference_dte","iv_0dte","iv_1_5dte",
            "iv_6_20dte","iv_21_365dte","expected_move_pct_1d","expected_move_dollars_1d",
            "expected_move_low","expected_move_high","realized_vol_60m","realized_vol_bars",
            "realized_vol_source_timestamp","realized_vol_bar_timestamp","iv_minus_realized_vol","reason","surface_json")
    result = dict(zip(keys, row))
    result.update(json.loads(result.pop("surface_json") or "{}"))
    for key in ("captured_at", "source_timestamp", "realized_vol_source_timestamp",
                "realized_vol_bar_timestamp"):
        if result[key] is not None:
            result[key] = result[key].isoformat()
    return result


def _cached_surface_payload(symbol: str, now: datetime | None = None) -> dict[str, Any]:
    """Return the durable surface with an honest *current* freshness verdict."""
    now = now or datetime.now(UTC)
    row = _latest_surface(symbol)
    if row is None:
        return {"symbol": symbol, "available": False, "confidence": "LOW",
                "reason": "no_persisted_surface"}
    source_ts = _parse_ts(row.get("source_timestamp"))
    age = (now - source_ts).total_seconds() if source_ts else None
    fresh = (row.get("confidence") in {"HIGH", "MEDIUM"} and age is not None
             and 0 <= age <= STALE_SECONDS)
    row.update({"symbol": symbol, "available": fresh,
                "age_seconds": round(age, 1) if age is not None else None,
                "reason": row.get("reason") or (None if fresh else "stale_persisted_surface")})
    return row


def _latest_trade_quote_flow(symbol: str, *, verified_only: bool = False) -> dict[str, Any] | None:
    ensure_tables()
    with engine.begin() as conn:
        row = conn.execute(text(
            f"SELECT captured_at,source,source_timestamp,confidence,n_trades,bucket_json,reason,evidence_json "
            f"FROM {FLOW_TABLE} WHERE symbol=:symbol "
            + ("AND confidence IN ('HIGH','MEDIUM') AND n_trades>0 " if verified_only else "")
            + "ORDER BY captured_at DESC LIMIT 1"),
            {"symbol": symbol}).fetchone()
    if not row:
        return None
    keys = ("captured_at", "source", "source_timestamp", "confidence", "n_trades",
            "bucket_json", "reason", "evidence_json")
    result = dict(zip(keys, row))
    for key in ("captured_at", "source_timestamp"):
        if result[key] is not None:
            result[key] = result[key].isoformat()
    result["buckets"] = json.loads(result.pop("bucket_json") or "{}")
    result["evidence"] = json.loads(result.pop("evidence_json") or "{}")
    result["guardrail"] = (
        "LIKELY buyer/seller initiated is based on an OPRA print at the attached NBBO. "
        "It does not establish opening/closing, institution, or multi-leg structure."
    )
    return result


def _cached_gamma_payload(symbol: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    row = _latest_gamma(symbol)
    if row is None:
        return {"symbol": symbol, "available": False, "confidence": "LOW",
                "reason": "no_persisted_gamma"}
    source_ts = _parse_ts(row.get("source_timestamp"))
    age = (now - source_ts).total_seconds() if source_ts else None
    # Gamma coverage can be MEDIUM on a deliberately bounded near-term map.
    # The report contract rejects LOW confidence; it must not discard a fresh,
    # numeric MEDIUM map and then claim gamma is unavailable.
    fresh = (row.get("confidence") in {"HIGH", "MEDIUM"} and age is not None
             and 0 <= age <= STALE_SECONDS)
    row.update({"symbol": symbol, "available": fresh,
                "age_seconds": round(age, 1) if age is not None else None,
                "reason": row.get("reason") or (None if fresh else "stale_persisted_gamma")})
    return row


def _cached_vol_payload(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    ensure_tables()
    with engine.begin() as conn:
        rows = conn.execute(text(
            f"SELECT DISTINCT ON (symbol) symbol,price,source,source_timestamp,reason "
            f"FROM {VOL_TABLE} ORDER BY symbol,captured_at DESC"), {}).fetchall()
    indices: dict[str, Any] = {}
    for symbol, price, _source, source_timestamp, reason in rows:
        stamp = source_timestamp.replace(tzinfo=UTC) if source_timestamp and source_timestamp.tzinfo is None else source_timestamp
        age = (now - stamp).total_seconds() if stamp else None
        fresh = price is not None and age is not None and 0 <= age <= STALE_SECONDS
        indices[symbol] = {"symbol": symbol, "price": price,
                           "source_timestamp": stamp.isoformat() if stamp else None,
                           "age_seconds": round(age, 1) if age is not None else None,
                           "fresh": fresh,
                           "reason": reason or (None if fresh else "stale_persisted_quote")}
    return {"available": any(item["fresh"] for item in indices.values()),
            "source": "Persisted ThetaData index snapshot price",
            "retrieved_at": now.isoformat(), "indices": indices}

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
                logger.info(
                    "[MarketStructure] critical capture complete surface_available=%d/2 vol_available=%s",
                    sum(1 for item in (result.get("surface") or {}).values() if item.get("available")),
                    bool((result.get("volatility") or {}).get("available")),
                )
        except Exception:  # noqa: BLE001
            logger.exception("[MarketStructure] minute capture failed")

    def recovery_tick() -> None:
        try:
            result = recover_critical_surface()
            if not result.get("recovered") and result.get("reason") != "market_closed":
                logger.error("[MarketStructure] critical surface recovery did not pass freshness")
        except Exception:  # noqa: BLE001
            logger.exception("[MarketStructure] critical surface recovery failed")

    def gamma_tick() -> None:
        try:
            result = capture_gamma_pair()
            if result.get("captured"):
                logger.info(
                    "[MarketStructure] bounded gamma capture complete available=%d/2",
                    sum(1 for item in (result.get("gamma") or {}).values()
                        if item.get("available")),
                )
        except Exception:  # noqa: BLE001
            logger.exception("[MarketStructure] bounded gamma capture failed")

    scheduler.add_job(
        tick, "cron", day_of_week="mon-fri", hour="8-15", minute="*",
        timezone=CT, id="market_structure_capture", replace_existing=True,
        coalesce=True, max_instances=1, misfire_grace_time=90,
        next_run_time=datetime.now(UTC),
    )
    scheduler.add_job(
        recovery_tick, "cron", day_of_week="mon-fri", hour="8-15", minute="*", second=35,
        timezone=CT, id="market_structure_surface_recovery", replace_existing=True,
        coalesce=True, max_instances=1, misfire_grace_time=45,
    )
    # A 20-second gap after the primary tick is a circuit breaker: when Theta
    # is slow, gamma may fail independently but cannot stale the surface/VIX.
    scheduler.add_job(
        gamma_tick, "cron", day_of_week="mon-fri", hour="8-15", minute="*", second=20,
        timezone=CT, id="market_structure_gamma_capture", replace_existing=True,
        coalesce=True, max_instances=1, misfire_grace_time=45,
        next_run_time=datetime.now(UTC) + timedelta(seconds=5),
    )
    logger.info(
        "[MarketStructure] registered isolated minute IV-surface/VIX and bounded SPY/QQQ gamma captures; "
        "both enforce the 08:30-15:05 market window"
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


@router.get("/surface/{symbol}")
def surface_symbol(symbol: str):
    symbol = symbol.upper()
    if symbol not in {"SPY", "QQQ"}:
        return {"available": False, "reason": "surface supports SPY and QQQ", "symbol": symbol}
    payload = _cached_surface_payload(symbol, datetime.now(UTC))
    if payload.get("available"):
        return payload
    # Report requests get one bounded, report-critical recovery attempt. This
    # is only reached after the cache has failed its freshness gate; it never
    # restarts the old slow gamma/flow sweep.
    rebuilt = build_volatility_surface(symbol, datetime.now(UTC))
    persist_surface(rebuilt)
    return rebuilt


@router.get("/surface/latest/{symbol}")
def latest_surface_symbol(symbol: str):
    symbol = symbol.upper()
    if symbol not in {"SPY", "QQQ"}:
        return {"available": False, "reason": "surface supports SPY and QQQ", "symbol": symbol}
    row = _latest_surface(symbol)
    return {"available": row is not None, "symbol": symbol, "surface": row}


@router.get("/flow/{symbol}")
def trade_quote_flow_symbol(symbol: str):
    symbol = symbol.upper()
    if symbol not in {"SPY", "QQQ"}:
        return {"available": False, "reason": "trade-quote flow supports SPY and QQQ", "symbol": symbol}
    row = _latest_trade_quote_flow(symbol)
    return {"available": row is not None, "symbol": symbol, "flow": row}


@router.get("/flow/latest/{symbol}")
def latest_trade_quote_flow_symbol(symbol: str):
    symbol = symbol.upper()
    if symbol not in {"SPY", "QQQ"}:
        return {"available": False, "reason": "trade-quote flow supports SPY and QQQ", "symbol": symbol}
    row = _latest_trade_quote_flow(symbol)
    return {"available": row is not None, "symbol": symbol, "flow": row}


@router.get("/cross-asset")
def cross_asset():
    """Fresh sector-relative and credit-proxy context for reports."""
    now = datetime.now(UTC)
    payload = fetch_cross_asset(now)
    assets = payload.get("assets") or {}
    spy = assets.get("SPY") or {}
    spy_prev = spy.get("prev_close")
    spy_ret = ((spy.get("price") / spy_prev - 1) * 100
               if spy.get("price") and spy_prev else None)
    rows = []
    for symbol in CROSS_ASSET_SYMBOLS:
        item = assets.get(symbol) or {"symbol": symbol}
        prev = item.get("prev_close")
        ret = ((item.get("price") / prev - 1) * 100
               if item.get("price") and prev else None)
        rows.append({**item, "day_return_pct": round(ret, 3) if ret is not None else None,
                     "relative_to_spy_pct": round(ret - spy_ret, 3)
                     if ret is not None and spy_ret is not None else None})
    return {**payload, "spy_day_return_pct": round(spy_ret, 3) if spy_ret is not None else None,
            "rows": rows,
            "interpretation_guardrail": "Use only fresh rows. Relative returns show leadership, not institutional flows or future certainty."}


@router.get("/report-readiness")
def report_readiness():
    """Single auditable contract for report-critical live data.

    Report writers use this before drafting.  It makes each required block
    explicit, prevents a missing field from silently disappearing, and keeps
    LOW/stale observations from influencing the thesis.
    """
    now = datetime.now(UTC)
    surface = {symbol: _cached_surface_payload(symbol, now) for symbol in ("SPY", "QQQ")}
    gamma = {symbol: _cached_gamma_payload(symbol, now) for symbol in ("SPY", "QQQ")}
    vol = _cached_vol_payload(now)
    cross = fetch_cross_asset(now)
    flow: dict[str, Any] = {}
    for symbol in ("SPY", "QQQ"):
        row = _latest_trade_quote_flow(symbol)
        stamp = _parse_ts((row or {}).get("source_timestamp"))
        age = (now - stamp).total_seconds() if stamp else None
        usable = bool(row and row.get("confidence") in {"HIGH", "MEDIUM"}
                      and age is not None and 0 <= age <= STALE_SECONDS)
        flow[symbol] = {**(row or {"symbol": symbol, "reason": "no_persisted_flow"}),
                        "available": usable,
                        "age_seconds": round(age, 1) if age is not None else None}

    checks = {
        "surface_spy": bool(surface["SPY"].get("available")),
        "surface_qqq": bool(surface["QQQ"].get("available")),
        "gamma_spy": bool(gamma["SPY"].get("available")),
        "gamma_qqq": bool(gamma["QQQ"].get("available")),
        "vix_family": all((vol.get("indices") or {}).get(symbol, {}).get("fresh")
                          for symbol in VOL_SYMBOLS),
        "sector_credit": bool(cross.get("available")),
        "flow_spy": bool(flow["SPY"].get("available")),
        "flow_qqq": bool(flow["QQQ"].get("available")),
        "smile_wings": all(item.get("available") and (item.get("smile") or {}).get("available")
                           and all((item.get("smile") or {}).get(key) is not None for key in
                                   ("put_25d_iv", "atm_iv", "call_25d_iv", "put_strike", "atm_strike", "call_strike"))
                           for item in surface.values()),
    }
    # All requested products are part of the audit, including producers that
    # have not yet been implemented. Absence must never be called readiness.
    outstanding = {
        "breadth": "awaiting verified constituent/VWAP observations",
        "profile": "awaiting timestamped consolidated trade profile",
        "macro": "awaiting verified rates/FX/commodities/MOVE observations",
        "contract_packages": "awaiting freshly qualified per-leg package",
        "paper_scorecard": "awaiting report-ledger query",
        "event_study": "awaiting completed historical study capture",
        "render_validation": "awaiting a full rendered report",
    }
    extended_checks = {}
    producer_details = {}
    try:
        from .full_options_report import latest_report
        from .report_contract import validate_rendered_report
        latest = latest_report()
        report_blocks = latest.get("report_blocks") or {}
        for name in tuple(outstanding):
            if name == "render_validation":
                ready = bool(report_blocks and validate_rendered_report(latest)["publishable"])
            else:
                block = report_blocks.get(name) or {}
                # Historical context is displayed but remains distinct from live readiness.
                ready = bool(block) and all(
                    item.get("status") == "live"
                    and (stamp := _parse_ts(item.get("source_timestamp"))) is not None
                    and 0 <= (now-stamp).total_seconds() <= STALE_SECONDS
                    for item in block.values())
                producer_details[name] = {field: {key: item.get(key) for key in
                    ("status", "source_timestamp", "reason")} for field,item in block.items()}
            extended_checks[name] = ready
            if ready:
                outstanding.pop(name)
    except Exception as exc:
        producer_details["read_error"] = type(exc).__name__
    if not checks["smile_wings"]:
        outstanding["smile_wings"] = "Fresh same-expiry observed smile wings unavailable; inspect surface.smile and producer reason"
    full_checks = {**checks, **extended_checks, **{key: False for key in outstanding}}
    # Flow is required to be visibly accounted for, but it cannot be silently
    # fabricated merely to pass a publish gate.  The reports receive both the
    # mandatory-core and optional-live-flow verdicts.
    mandatory_core = ("surface_spy", "surface_qqq", "gamma_spy", "gamma_qqq",
                      "vix_family", "sector_credit")
    return {
        "retrieved_at": now.isoformat(), "freshness_limit_seconds": STALE_SECONDS,
        "required_checks": full_checks,
        "all_requested_ready": all(full_checks.values()),
        "outstanding_producers": outstanding,
        "producer_details": producer_details,
        "implemented_collectors": ["constituent_breadth", "observed_trade_profile", "macro", "candidate_surfaces", "futures", "report_paper_ledger", "historical_event_study", "dark_png_renderer"],
        "core_ready": all(checks[key] for key in mandatory_core),
        "flow_ready": checks["flow_spy"] and checks["flow_qqq"],
        "missing_core": [key for key in mandatory_core if not checks[key]],
        "missing_flow": [key for key in ("flow_spy", "flow_qqq") if not checks[key]],
        "surface": surface, "gamma": gamma, "volatility": vol,
        "cross_asset": cross, "flow": flow,
        "writer_rule": (
            "Every named block must be rendered from this payload or listed once in Data Integrity. "
            "Never replace an unavailable block with a decorative image or inferred data."
        ),
    }


@router.get("/vol-indices")
def vol_indices():
    payload = _cached_vol_payload(datetime.now(UTC))
    if payload.get("available"):
        return payload
    refreshed = fetch_vol_indices(datetime.now(UTC))
    persist_vol(refreshed)
    return refreshed


@router.get("/gamma/{symbol}")
def gamma_symbol(symbol: str):
    symbol = symbol.upper()
    if symbol not in SYMBOLS:
        return {"available": False, "reason": f"unsupported symbol {symbol}",
                "supported": SYMBOLS}
    return _cached_gamma_payload(symbol, datetime.now(UTC))


@router.get("/latest/{symbol}")
def latest_symbol(symbol: str):
    symbol = symbol.upper()
    if symbol not in SYMBOLS:
        return {"available": False, "reason": f"unsupported symbol {symbol}",
                "supported": SYMBOLS}
    row = _latest_gamma(symbol)
    return {"available": row is not None, "symbol": symbol, "snapshot": row}


@router.get("/report-contract")
def report_contract_schema():
    from .report_contract import REQUIREMENTS, CONTRACT_VERSION
    from .report_policy import policy_identity, PRESENTATION
    return {"contract_version": CONTRACT_VERSION, "required_fields": REQUIREMENTS,
            "report_policy":policy_identity(),"presentation":PRESENTATION,
            "render_rule": "Use canonical block headings with underscores replaced by spaces; render every field name and its value or explicit unavailable reason."}


@router.post("/validate-report")
def validate_intraday_report(payload: dict[str, Any]):
    """Pure publication check for submitted final intraday report; no orders or writes."""
    from .report_contract import validate_rendered_report
    return validate_rendered_report(payload)
