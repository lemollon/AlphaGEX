"""SpreadWorks API routes.

Endpoints
---------
GET  /api/spreadworks/market-status        Market open/closed + last data timestamp
GET  /api/spreadworks/candles              OHLCV candle data (live or cached)
GET  /api/spreadworks/gex                  GEX levels (live or cached)
GET  /api/spreadworks/expirations          Available option expirations
GET  /api/spreadworks/chain                Option chain with greeks (live or cached)
GET  /api/spreadworks/gex-suggest          Auto-suggest strikes from GEX levels
POST /api/spreadworks/calculate            Spread P&L / Greeks (BS or chain-aware)
GET  /api/spreadworks/alerts               Active price alerts
POST /api/spreadworks/alerts               Create a new alert
POST /api/spreadworks/alerts/{id}/trigger  Mark alert as triggered
DELETE /api/spreadworks/alerts/{id}        Delete an alert
GET  /api/spreadworks/positions            Saved spread positions
POST /api/spreadworks/positions            Save a new position
DELETE /api/spreadworks/positions/{id}     Delete a position
GET  /api/spreadworks/positions/{id}/pnl   Live unrealised P&L for a position
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

_CT = ZoneInfo("America/Chicago")


def _now_ct() -> datetime:
    """Current time in Central Time (America/Chicago)."""
    return datetime.now(_CT)


def _today_ct() -> date:
    """Today's date in Central Time."""
    return _now_ct().date()

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .db import get_db, SessionLocal
from .models import Position, DailyMark, QuoteCache, CandleCache, GexCache, ChainCache

logger = logging.getLogger("spreadworks")

router = APIRouter(prefix="/api/spreadworks", tags=["SpreadWorks"])

TRADIER_TOKEN = os.getenv("TRADIER_TOKEN", "")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID", "")
TRADIER_BASE = "https://api.tradier.com/v1"
ALPHAGEX_BASE_URL = os.getenv("ALPHAGEX_BASE_URL", "http://localhost:8000")
RISK_FREE_RATE = float(os.getenv("RISK_FREE_RATE", "0.05"))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tradier_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}


async def _tradier_get(request: Request, path: str, params: dict | None = None):
    """GET from Tradier API via the shared httpx client."""
    http = request.app.state.http
    resp = await http.get(
        f"{TRADIER_BASE}{path}",
        headers=_tradier_headers(),
        params=params or {},
    )
    if resp.status_code != 200:
        raise HTTPException(502, f"Tradier error {resp.status_code}: {resp.text[:200]}")
    return resp.json()


async def _get_quote(request: Request, symbol: str) -> dict:
    """Fetch a single quote from Tradier."""
    data = await _tradier_get(request, "/markets/quotes", {"symbols": symbol})
    quotes = data.get("quotes", {})
    q = quotes.get("quote", {}) if quotes else {}
    if isinstance(q, list):
        q = q[0] if q else {}
    return q


# ---------------------------------------------------------------------------
# Cache helpers — non-blocking write-through on every successful live fetch
# ---------------------------------------------------------------------------


def _cache_write(fn):
    """Fire-and-forget DB cache write. Never slow down the response."""
    if SessionLocal is None:
        return
    try:
        db = SessionLocal()
        try:
            fn(db)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.debug("Cache write failed: %s", e)
        finally:
            db.close()
    except Exception:
        pass


def _cache_candles(symbol: str, interval: str, candles: list, last_price: float | None):
    def _write(db: Session):
        from sqlalchemy.dialects.postgresql import insert
        stmt = insert(CandleCache).values(
            symbol=symbol, interval=interval,
            candles_json=json.dumps(candles),
            last_price=last_price,
            fetched_at=datetime.now(timezone.utc),
        ).on_conflict_do_update(
            index_elements=["symbol", "interval"],
            set_=dict(
                candles_json=json.dumps(candles),
                last_price=last_price,
                fetched_at=datetime.now(timezone.utc),
            ),
        )
        db.execute(stmt)
    _cache_write(_write)


def _cache_quote(symbol: str, last: float | None):
    def _write(db: Session):
        from sqlalchemy.dialects.postgresql import insert
        stmt = insert(QuoteCache).values(
            symbol=symbol, last=last,
            fetched_at=datetime.now(timezone.utc),
        ).on_conflict_do_update(
            index_elements=["symbol"],
            set_=dict(last=last, fetched_at=datetime.now(timezone.utc)),
        )
        db.execute(stmt)
    _cache_write(_write)


def _cache_gex(symbol: str, data: dict):
    def _write(db: Session):
        from sqlalchemy.dialects.postgresql import insert
        stmt = insert(GexCache).values(
            symbol=symbol,
            flip_point=data.get("flip_point"),
            call_wall=data.get("call_wall"),
            put_wall=data.get("put_wall"),
            gamma_regime=data.get("gamma_regime"),
            spot_price=data.get("spot_price"),
            vix=data.get("vix"),
            source=data.get("source"),
            fetched_at=datetime.now(timezone.utc),
        ).on_conflict_do_update(
            index_elements=["symbol"],
            set_=dict(
                flip_point=data.get("flip_point"),
                call_wall=data.get("call_wall"),
                put_wall=data.get("put_wall"),
                gamma_regime=data.get("gamma_regime"),
                spot_price=data.get("spot_price"),
                vix=data.get("vix"),
                source=data.get("source"),
                fetched_at=datetime.now(timezone.utc),
            ),
        )
        db.execute(stmt)
    _cache_write(_write)


def _cache_chain(symbol: str, expiration: str, chain_data: dict):
    def _write(db: Session):
        from sqlalchemy.dialects.postgresql import insert
        stmt = insert(ChainCache).values(
            symbol=symbol, expiration=expiration,
            chain_json=json.dumps(chain_data),
            fetched_at=datetime.now(timezone.utc),
        ).on_conflict_do_update(
            index_elements=["symbol", "expiration"],
            set_=dict(
                chain_json=json.dumps(chain_data),
                fetched_at=datetime.now(timezone.utc),
            ),
        )
        db.execute(stmt)
    _cache_write(_write)


def _read_cached_candles(symbol: str, interval: str = "15min") -> dict | None:
    if SessionLocal is None:
        return None
    try:
        db = SessionLocal()
        try:
            row = db.query(CandleCache).filter(
                CandleCache.symbol == symbol,
                CandleCache.interval == interval,
            ).first()
            if row and row.candles_json:
                return {
                    "candles": json.loads(row.candles_json),
                    "last_price": row.last_price,
                    "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
                }
        finally:
            db.close()
    except Exception:
        pass
    return None


def _read_cached_gex(symbol: str) -> dict | None:
    if SessionLocal is None:
        return None
    try:
        db = SessionLocal()
        try:
            row = db.query(GexCache).filter(GexCache.symbol == symbol).first()
            if row:
                return {
                    "flip_point": row.flip_point,
                    "call_wall": row.call_wall,
                    "put_wall": row.put_wall,
                    "gamma_regime": row.gamma_regime,
                    "spot_price": row.spot_price,
                    "vix": row.vix,
                    "source": f"{row.source}_cached",
                    "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
                }
        finally:
            db.close()
    except Exception:
        pass
    return None


def _read_cached_chain(symbol: str, expiration: str) -> dict | None:
    if SessionLocal is None:
        return None
    try:
        db = SessionLocal()
        try:
            row = db.query(ChainCache).filter(
                ChainCache.symbol == symbol,
                ChainCache.expiration == expiration,
            ).first()
            if row and row.chain_json:
                data = json.loads(row.chain_json)
                data["fetched_at"] = row.fetched_at.isoformat() if row.fetched_at else None
                return data
        finally:
            db.close()
    except Exception:
        pass
    return None


def _read_cached_quote(symbol: str) -> dict | None:
    if SessionLocal is None:
        return None
    try:
        db = SessionLocal()
        try:
            row = db.query(QuoteCache).filter(QuoteCache.symbol == symbol).first()
            if row:
                return {
                    "last": row.last,
                    "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
                }
        finally:
            db.close()
    except Exception:
        pass
    return None


def _is_market_open_now() -> bool:
    """Check if US equity market is currently open (Mon-Fri 9:30-16:00 ET)."""
    from zoneinfo import ZoneInfo
    et = datetime.now(ZoneInfo("America/New_York"))
    if et.weekday() >= 5:  # Sat/Sun
        return False
    mins = et.hour * 60 + et.minute
    return 570 <= mins < 960  # 9:30 - 16:00


def _last_market_close() -> str:
    """Return ISO datetime of the most recent market close (4:00 PM ET)."""
    from zoneinfo import ZoneInfo
    et = datetime.now(ZoneInfo("America/New_York"))
    # Walk back to the most recent weekday at 16:00
    close_time = et.replace(hour=16, minute=0, second=0, microsecond=0)
    if et.hour < 16 or et.weekday() >= 5:
        close_time -= timedelta(days=1)
    while close_time.weekday() >= 5:
        close_time -= timedelta(days=1)
    return close_time.isoformat()


# ---------------------------------------------------------------------------
# 0. Market status
# ---------------------------------------------------------------------------


@router.get("/market-status")
async def market_status():
    """Return whether the market is open and the last close timestamp."""
    is_open = _is_market_open_now()
    last_close = _last_market_close()

    # Check what's in cache
    cached_quote = _read_cached_quote("SPY")
    data_as_of = None
    if cached_quote and cached_quote.get("fetched_at"):
        data_as_of = cached_quote["fetched_at"]

    return {
        "is_open": is_open,
        "last_close": last_close,
        "data_as_of": data_as_of,
        "message": "Market is open" if is_open else f"Market closed · Data as of {data_as_of or last_close}",
    }


# ---------------------------------------------------------------------------
# 1. Candles — live fetch with write-through cache + fallback
# ---------------------------------------------------------------------------


@router.get("/candles")
async def get_candles(request: Request, symbol: str = "SPY", interval: str = "15min"):
    """Return 15-min candles. Live from Tradier during market hours, cached otherwise."""
    start_date = (_today_ct() - timedelta(days=14)).isoformat()

    candles: list[dict] = []
    last_price = None
    data_as_of = None

    try:
        ts_data = await _tradier_get(
            request,
            "/markets/timesales",
            {
                "symbol": symbol,
                "interval": "15min",
                "start": start_date,
                "session_filter": "open",
            },
        )
        series = ts_data.get("series") or {}
        bars = series.get("data") or []
        if isinstance(bars, dict):
            bars = [bars]

        candles = bars
        if candles:
            last_price = candles[-1].get("close")
            # Write-through cache
            _cache_candles(symbol, interval, candles, last_price)
            if last_price:
                _cache_quote(symbol, last_price)
    except Exception:
        pass

    # Fallback: if timesales returned nothing, try quote then cache
    if not candles:
        try:
            q = await _get_quote(request, symbol)
            last_price = q.get("last")
            if last_price:
                _cache_quote(symbol, last_price)
        except Exception:
            pass

    # If still no candles (market closed, API down, etc.), read from cache
    if not candles:
        cached = _read_cached_candles(symbol, interval)
        if cached:
            candles = cached["candles"]
            last_price = last_price or cached["last_price"]
            data_as_of = cached.get("fetched_at")

    # If we have no spot price at all, try cached quote
    if not last_price:
        cached_q = _read_cached_quote(symbol)
        if cached_q:
            last_price = cached_q["last"]
            data_as_of = data_as_of or cached_q.get("fetched_at")

    return {
        "symbol": symbol,
        "candles": candles,
        "last_price": last_price,
        "data_as_of": data_as_of,
    }


# ---------------------------------------------------------------------------
# 2. GEX levels (proxy from AlphaGEX)
# ---------------------------------------------------------------------------


@router.get("/gex")
async def get_gex(request: Request, symbol: str = "SPY"):
    """Proxy GEX levels from AlphaGEX. Falls back to cache when unavailable."""
    import httpx

    http = request.app.state.http
    _timeout = 5.0

    # Try WATCHTOWER first
    try:
        resp = await http.get(
            f"{ALPHAGEX_BASE_URL}/api/watchtower/gamma",
            params={"symbol": symbol, "expiration": "today"},
            timeout=_timeout,
        )
        if resp.status_code == 200:
            body = resp.json()
            d = body.get("data", {})
            ms = d.get("market_structure", {})
            fp_obj = ms.get("flip_point", {})
            gw = ms.get("gamma_walls", {})
            result = {
                "flip_point": fp_obj.get("current") if isinstance(fp_obj, dict) else fp_obj,
                "call_wall": gw.get("call_wall") if isinstance(gw, dict) else None,
                "put_wall": gw.get("put_wall") if isinstance(gw, dict) else None,
                "gamma_regime": d.get("gamma_regime") or ms.get("gamma_regime"),
                "spot_price": d.get("spot_price"),
                "vix": d.get("vix"),
                "source": "watchtower",
            }
            _cache_gex(symbol, result)
            return result
    except httpx.TimeoutException:
        pass
    except Exception:
        pass

    # Fallback to simple GEX endpoint
    try:
        resp = await http.get(
            f"{ALPHAGEX_BASE_URL}/api/gex/{symbol}",
            timeout=_timeout,
        )
        if resp.status_code == 200:
            body = resp.json()
            d = body.get("data", body)
            result = {
                "flip_point": d.get("flip_point"),
                "call_wall": d.get("call_wall"),
                "put_wall": d.get("put_wall"),
                "gamma_regime": d.get("regime") or d.get("gamma_regime"),
                "spot_price": d.get("spot_price"),
                "vix": d.get("vix"),
                "source": "gex",
            }
            _cache_gex(symbol, result)
            return result
    except httpx.TimeoutException:
        pass
    except Exception:
        pass

    # All live sources failed — try cache
    cached = _read_cached_gex(symbol)
    if cached:
        return cached

    return {"error": "GEX data unavailable", "detail": "Could not reach AlphaGEX backend"}


# ---------------------------------------------------------------------------
# 3. Expirations
# ---------------------------------------------------------------------------


@router.get("/expirations")
async def get_expirations(request: Request, symbol: str = "SPY"):
    """Return available option expirations from Tradier."""
    data = await _tradier_get(
        request,
        "/markets/options/expirations",
        {"symbol": symbol, "includeAllRoots": "true"},
    )
    exps = data.get("expirations", {})
    if exps is None:
        exps = {}
    date_list = exps.get("date", [])
    if isinstance(date_list, str):
        date_list = [date_list]
    return {"symbol": symbol, "expirations": date_list}


# ---------------------------------------------------------------------------
# 4. Option chain — returns full option data with greeks
# ---------------------------------------------------------------------------


async def _fetch_chain_raw(request: Request, symbol: str, expiration: str) -> list[dict]:
    """Return raw option list from Tradier chain endpoint."""
    data = await _tradier_get(
        request,
        "/markets/options/chains",
        {"symbol": symbol, "expiration": expiration, "greeks": "true"},
    )
    options = data.get("options", {})
    if options is None:
        options = {}
    option_list = options.get("option", [])
    if isinstance(option_list, dict):
        option_list = [option_list]
    return option_list


@router.get("/chain")
async def get_chain(request: Request, symbol: str = "SPY", expiration: str = ""):
    """Return strikes and full option data. Falls back to cache when unavailable."""
    if not expiration:
        raise HTTPException(400, "expiration query param is required")

    option_list = None
    try:
        option_list = await _fetch_chain_raw(request, symbol, expiration)
    except Exception:
        pass

    if option_list:
        # Build per-strike data with greeks
        strikes_set: set[float] = set()
        options_by_strike: dict[float, dict] = {}
        for o in option_list:
            strike = o.get("strike")
            if strike is None:
                continue
            strikes_set.add(strike)
            otype = o.get("option_type", "").lower()
            greeks = o.get("greeks", {}) or {}
            entry = {
                "bid": o.get("bid"),
                "ask": o.get("ask"),
                "mid": round((o.get("bid", 0) + o.get("ask", 0)) / 2, 4) if o.get("bid") is not None else None,
                "last": o.get("last"),
                "volume": o.get("volume"),
                "open_interest": o.get("open_interest"),
                "iv": greeks.get("mid_iv") or greeks.get("smv_vol"),
                "delta": greeks.get("delta"),
                "gamma": greeks.get("gamma"),
                "theta": greeks.get("theta"),
                "vega": greeks.get("vega"),
            }
            if strike not in options_by_strike:
                options_by_strike[strike] = {}
            options_by_strike[strike][otype] = entry

        strikes = sorted(strikes_set)
        result = {
            "symbol": symbol,
            "expiration": expiration,
            "strikes": strikes,
            "options": options_by_strike,
        }
        # Write-through cache (convert float keys to str for JSON)
        cache_data = {
            "strikes": strikes,
            "options": {str(k): v for k, v in options_by_strike.items()},
        }
        _cache_chain(symbol, expiration, cache_data)
        return result

    # Live fetch failed — try cache
    cached = _read_cached_chain(symbol, expiration)
    if cached:
        # Reconstruct with float keys
        raw_options = cached.get("options", {})
        options_by_strike = {}
        for k, v in raw_options.items():
            try:
                options_by_strike[float(k)] = v
            except (ValueError, TypeError):
                options_by_strike[k] = v
        return {
            "symbol": symbol,
            "expiration": expiration,
            "strikes": cached.get("strikes", []),
            "options": options_by_strike,
            "data_as_of": cached.get("fetched_at"),
        }

    raise HTTPException(502, "Option chain unavailable and no cached data")


# ---------------------------------------------------------------------------
# 5. GEX-suggested strikes
# ---------------------------------------------------------------------------


@router.get("/gex-suggest")
async def gex_suggest(
    request: Request,
    symbol: str = "SPY",
    strategy: str = "double_diagonal",
):
    """Auto-generate strike suggestions from GEX levels."""
    gex = await get_gex(request, symbol)
    if "error" in gex:
        raise HTTPException(502, gex["error"])
    flip = gex.get("flip_point")
    call_wall = gex.get("call_wall")
    put_wall = gex.get("put_wall")
    spot = gex.get("spot_price")
    regime = gex.get("gamma_regime")

    if not flip or not spot:
        raise HTTPException(
            422,
            "GEX data incomplete — flip_point and spot_price required for suggestions",
        )

    if not call_wall:
        call_wall = spot + (spot * 0.01)
    if not put_wall:
        put_wall = spot - (spot * 0.01)

    def _round_strike(v: float) -> float:
        return round(v * 2) / 2

    today = _today_ct()
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0:
        days_until_friday = 7
    front_exp = (today + timedelta(days=days_until_friday)).isoformat()
    back_exp = (today + timedelta(days=days_until_friday + 7)).isoformat()

    wing_offset = 3.0 if regime and "POSITIVE" in str(regime).upper() else 5.0

    if strategy == "double_diagonal":
        short_put = _round_strike(put_wall)
        short_call = _round_strike(call_wall)
        long_put = _round_strike(short_put - wing_offset)
        long_call = _round_strike(short_call + wing_offset)

        legs = {
            "long_put_strike": long_put,
            "short_put_strike": short_put,
            "short_call_strike": short_call,
            "long_call_strike": long_call,
            "short_expiration": front_exp,
            "long_expiration": back_exp,
        }
        rationale = (
            f"Short strikes at GEX walls (put wall ${short_put}, call wall ${short_call}). "
            f"Long wings ${wing_offset} wide. "
            f"Front exp {front_exp}, back exp {back_exp}. "
            f"Regime: {regime or 'UNKNOWN'}."
        )
    elif strategy == "iron_condor":
        short_put = _round_strike(put_wall)
        short_call = _round_strike(call_wall)
        long_put = _round_strike(short_put - wing_offset)
        long_call = _round_strike(short_call + wing_offset)

        legs = {
            "long_put_strike": long_put,
            "short_put_strike": short_put,
            "short_call_strike": short_call,
            "long_call_strike": long_call,
            "expiration": front_exp,
        }
        rationale = (
            f"Iron Condor: short strikes at GEX walls "
            f"(put wall ${short_put}, call wall ${short_call}). "
            f"Long wings ${wing_offset} wide. "
            f"Single exp {front_exp}. "
            f"Regime: {regime or 'UNKNOWN'}."
        )
    else:  # double_calendar
        put_strike = _round_strike(put_wall)
        call_strike = _round_strike(call_wall)

        legs = {
            "put_strike": put_strike,
            "call_strike": call_strike,
            "front_expiration": front_exp,
            "back_expiration": back_exp,
        }
        rationale = (
            f"Calendar strikes at GEX walls (put ${put_strike}, call ${call_strike}). "
            f"Front {front_exp}, back {back_exp}. "
            f"Regime: {regime or 'UNKNOWN'}."
        )

    return {
        "symbol": symbol,
        "strategy": strategy,
        "legs": legs,
        "flip_point": flip,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "gamma_regime": regime,
        "spot_price": spot,
        "rationale": rationale,
    }


# ---------------------------------------------------------------------------
# 6. Calculate spread P&L (Black-Scholes or chain-aware)
# ---------------------------------------------------------------------------

_SQRT2PI = math.sqrt(2 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT2PI


def _bs_price(
    S: float, K: float, T: float, r: float, sigma: float, is_call: bool
) -> float:
    if T <= 0 or sigma <= 0:
        return max(0, S - K) if is_call else max(0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if is_call:
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def _bs_greeks(
    S: float, K: float, T: float, r: float, sigma: float, is_call: bool
) -> dict:
    if T <= 0 or sigma <= 0:
        intrinsic = max(0, S - K) if is_call else max(0, K - S)
        return {"delta": (1.0 if intrinsic > 0 else 0.0) * (1 if is_call else -1),
                "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    nd1 = _norm_pdf(d1)

    delta = _norm_cdf(d1) if is_call else _norm_cdf(d1) - 1.0
    gamma = nd1 / (S * sigma * sqrtT)
    theta = (-(S * nd1 * sigma) / (2 * sqrtT)
             - r * K * math.exp(-r * T) * _norm_cdf(d2 if is_call else -d2)
             * (1 if is_call else -1)) / 365.0
    vega = S * nd1 * sqrtT / 100.0

    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}


def _scan_pnl_profile(
    strategy: str,
    S: float,
    strikes: dict[str, float],
    expirations: dict[str, float],
    r: float,
    sigma: float,
    entry_cost: float,
    n: int,
) -> dict:
    """Scan underlying prices to build P&L curve, breakevens, max profit/loss."""
    today_date = _today_ct()

    def _tte(d: str) -> float:
        exp = datetime.strptime(d, "%Y-%m-%d").date()
        return max((exp - today_date).days, 0) / 365.0

    if strategy == "double_diagonal":
        lp, sp = strikes["lp"], strikes["sp"]
        sc, lc = strikes["sc"], strikes["lc"]
        T_short = _tte(expirations["short"])
        T_long = _tte(expirations["long"])
        T_remaining = max(T_long - T_short, 1 / 365.0)
        scan_lo = min(lp, sp, sc, lc) - 20
        scan_hi = max(lp, sp, sc, lc) + 20
    elif strategy == "iron_condor":
        lp, sp = strikes["lp"], strikes["sp"]
        sc, lc = strikes["sc"], strikes["lc"]
        T_exp = _tte(expirations["exp"])
        scan_lo = min(lp, sp, sc, lc) - 20
        scan_hi = max(lp, sp, sc, lc) + 20
    else:
        ps, cs = strikes["ps"], strikes["cs"]
        T_front = _tte(expirations["front"])
        T_back = _tte(expirations["back"])
        T_remaining = max(T_back - T_front, 1 / 365.0)
        scan_lo = min(ps, cs) - 20
        scan_hi = max(ps, cs) + 20

    curve = []
    max_profit = 0.0
    max_loss = 0.0
    lower_be = None
    upper_be = None
    prev_pnl = None
    profitable_count = 0
    total_count = 0

    for px_int in range(int(scan_lo * 10), int(scan_hi * 10) + 1):
        px = px_int / 10.0

        if strategy == "double_diagonal":
            pnl = (
                _bs_price(px, lp, T_remaining, r, sigma, False)
                - max(0, sp - px)
                - max(0, px - sc)
                + _bs_price(px, lc, T_remaining, r, sigma, True)
                - entry_cost
            ) * 100 * n
        elif strategy == "iron_condor":
            # Iron Condor at expiration: all intrinsic
            pnl = (
                max(0, lp - px)   # long put payoff
                - max(0, sp - px)  # short put payoff
                - max(0, px - sc)  # short call payoff
                + max(0, px - lc)  # long call payoff
                + entry_cost       # credit received (entry_cost is negative for credit)
            ) * 100 * n
        else:
            pnl = (
                -max(0, ps - px)
                + _bs_price(px, ps, T_remaining, r, sigma, False)
                - max(0, px - cs)
                + _bs_price(px, cs, T_remaining, r, sigma, True)
                - entry_cost
            ) * 100 * n

        # Sample every $1 for the curve (every 10th point)
        if px_int % 10 == 0:
            curve.append({"price": px, "pnl": round(pnl, 2)})

        if pnl > max_profit:
            max_profit = pnl
        if pnl < max_loss:
            max_loss = pnl
        if pnl > 0:
            profitable_count += 1
        total_count += 1

        if prev_pnl is not None:
            if prev_pnl < 0 <= pnl or prev_pnl >= 0 > pnl:
                if lower_be is None:
                    lower_be = px
                else:
                    upper_be = px
        prev_pnl = pnl

    prob = profitable_count / total_count if total_count > 0 else None
    return {
        "max_profit": round(max_profit, 2),
        "max_loss": round(max_loss, 2),
        "lower_breakeven": round(lower_be, 2) if lower_be else None,
        "upper_breakeven": round(upper_be, 2) if upper_be else None,
        "probability_of_profit": round(prob, 4) if prob is not None else None,
        "pnl_curve": curve,
    }


def _lookup_chain_mid(options: dict, strike: float, otype: str) -> float | None:
    """Look up mid price from chain options dict."""
    strike_data = options.get(str(strike)) or options.get(strike)
    if not strike_data:
        return None
    leg = strike_data.get(otype)
    if not leg:
        return None
    return leg.get("mid")


def _lookup_chain_iv(options: dict, strike: float, otype: str) -> float | None:
    """Look up implied vol from chain options dict."""
    strike_data = options.get(str(strike)) or options.get(strike)
    if not strike_data:
        return None
    leg = strike_data.get(otype)
    if not leg:
        return None
    return leg.get("iv")


class CalcRequest(BaseModel):
    symbol: str = "SPY"
    strategy: str  # double_diagonal | double_calendar | iron_condor
    contracts: int = 1
    legs: dict[str, Any]
    spot_price: float | None = None
    input_mode: str = "manual"
    use_chain_prices: bool = False
    chain_options: dict[str, Any] | None = None  # from /chain endpoint


@router.post("/calculate")
async def calculate_spread(request: Request, body: CalcRequest):
    """Calculate P&L profile, breakevens, and Greeks for a spread.

    When ``use_chain_prices`` is True and ``chain_options`` is provided,
    uses actual Tradier mid prices and IV instead of flat Black-Scholes.
    """
    S = body.spot_price
    if not S:
        gex = await get_gex(request, body.symbol)
        if "error" in gex:
            raise HTTPException(502, "GEX data unavailable — cannot determine spot price")
        S = gex.get("spot_price")
        if not S:
            raise HTTPException(422, "spot_price required")

    r = RISK_FREE_RATE
    default_sigma = 0.20
    legs = body.legs
    n = body.contracts
    today_date = _today_ct()
    chain_opts = body.chain_options or {}

    def _tte(d: str) -> float:
        exp = datetime.strptime(d, "%Y-%m-%d").date()
        return max((exp - today_date).days, 0) / 365.0

    def _price_or_bs(strike: float, T: float, is_call: bool, exp_str: str) -> tuple[float, float, bool]:
        """Return (price, iv, is_theoretical) using chain if available, else Black-Scholes."""
        otype = "call" if is_call else "put"
        # Try chain-aware pricing
        if body.use_chain_prices and chain_opts:
            exp_opts = chain_opts.get(exp_str, chain_opts)
            mid = _lookup_chain_mid(exp_opts, strike, otype)
            iv = _lookup_chain_iv(exp_opts, strike, otype)
            if mid is not None and mid > 0:
                sigma_used = iv if iv and iv > 0 else default_sigma
                return mid, sigma_used, False
        # Fallback: use per-leg IV from chain if available
        sigma = default_sigma
        if chain_opts:
            exp_opts = chain_opts.get(exp_str, chain_opts)
            iv = _lookup_chain_iv(exp_opts, strike, otype)
            if iv and iv > 0:
                sigma = iv
        return _bs_price(S, strike, T, r, sigma, is_call), sigma, True

    if body.strategy == "double_diagonal":
        lp = float(legs.get("longPutStrike") or legs.get("long_put_strike", 0))
        sp = float(legs.get("shortPutStrike") or legs.get("short_put_strike", 0))
        sc = float(legs.get("shortCallStrike") or legs.get("short_call_strike", 0))
        lc = float(legs.get("longCallStrike") or legs.get("long_call_strike", 0))
        short_exp = str(legs.get("shortExpiration") or legs.get("short_expiration", ""))
        long_exp = str(legs.get("longExpiration") or legs.get("long_expiration", ""))

        if not all([lp, sp, sc, lc, short_exp, long_exp]):
            raise HTTPException(422, "All 4 strikes and 2 expirations required")

        T_short = _tte(short_exp)
        T_long = _tte(long_exp)

        p_lp, iv_lp, theo_lp = _price_or_bs(lp, T_long, False, long_exp)
        p_sp, iv_sp, theo_sp = _price_or_bs(sp, T_short, False, short_exp)
        p_sc, iv_sc, theo_sc = _price_or_bs(sc, T_short, True, short_exp)
        p_lc, iv_lc, theo_lc = _price_or_bs(lc, T_long, True, long_exp)

        entry_cost = p_lp + p_lc - p_sp - p_sc
        net_debit = entry_cost * 100 * n

        # Greeks using per-leg IV
        g_lp = _bs_greeks(S, lp, T_long, r, iv_lp, False)
        g_sp = _bs_greeks(S, sp, T_short, r, iv_sp, False)
        g_sc = _bs_greeks(S, sc, T_short, r, iv_sc, True)
        g_lc = _bs_greeks(S, lc, T_long, r, iv_lc, True)

        greeks = {
            k: round((g_lp[k] - g_sp[k] - g_sc[k] + g_lc[k]) * n, 6)
            for k in ("delta", "gamma", "theta", "vega")
        }

        # Use average IV for P&L curve
        avg_sigma = sum([iv_lp, iv_sp, iv_sc, iv_lc]) / 4
        profile = _scan_pnl_profile(
            "double_diagonal", S,
            {"lp": lp, "sp": sp, "sc": sc, "lc": lc},
            {"short": short_exp, "long": long_exp},
            r, avg_sigma, entry_cost, n,
        )

        leg_detail = [
            {"leg": "Long Put", "strike": lp, "exp": long_exp, "price": round(p_lp, 4), "iv": round(iv_lp, 4), "theoretical": theo_lp},
            {"leg": "Short Put", "strike": sp, "exp": short_exp, "price": round(p_sp, 4), "iv": round(iv_sp, 4), "theoretical": theo_sp},
            {"leg": "Short Call", "strike": sc, "exp": short_exp, "price": round(p_sc, 4), "iv": round(iv_sc, 4), "theoretical": theo_sc},
            {"leg": "Long Call", "strike": lc, "exp": long_exp, "price": round(p_lc, 4), "iv": round(iv_lc, 4), "theoretical": theo_lc},
        ]

    elif body.strategy == "iron_condor":
        lp = float(legs.get("longPutStrike") or legs.get("long_put_strike", 0))
        sp = float(legs.get("shortPutStrike") or legs.get("short_put_strike", 0))
        sc = float(legs.get("shortCallStrike") or legs.get("short_call_strike", 0))
        lc = float(legs.get("longCallStrike") or legs.get("long_call_strike", 0))
        exp = str(legs.get("expiration") or "")

        if not all([lp, sp, sc, lc, exp]):
            raise HTTPException(422, "All 4 strikes and expiration required for Iron Condor")

        T_exp = _tte(exp)

        p_lp, iv_lp, theo_lp = _price_or_bs(lp, T_exp, False, exp)
        p_sp, iv_sp, theo_sp = _price_or_bs(sp, T_exp, False, exp)
        p_sc, iv_sc, theo_sc = _price_or_bs(sc, T_exp, True, exp)
        p_lc, iv_lc, theo_lc = _price_or_bs(lc, T_exp, True, exp)

        # IC is a credit strategy: sell short legs, buy long wings
        entry_cost = p_lp + p_lc - p_sp - p_sc  # negative = net credit
        net_debit = entry_cost * 100 * n

        g_lp = _bs_greeks(S, lp, T_exp, r, iv_lp, False)
        g_sp = _bs_greeks(S, sp, T_exp, r, iv_sp, False)
        g_sc = _bs_greeks(S, sc, T_exp, r, iv_sc, True)
        g_lc = _bs_greeks(S, lc, T_exp, r, iv_lc, True)

        greeks = {
            k: round((g_lp[k] - g_sp[k] - g_sc[k] + g_lc[k]) * n, 6)
            for k in ("delta", "gamma", "theta", "vega")
        }

        avg_sigma = sum([iv_lp, iv_sp, iv_sc, iv_lc]) / 4
        profile = _scan_pnl_profile(
            "iron_condor", S,
            {"lp": lp, "sp": sp, "sc": sc, "lc": lc},
            {"exp": exp},
            r, avg_sigma, entry_cost, n,
        )

        leg_detail = [
            {"leg": "Long Put", "strike": lp, "exp": exp, "price": round(p_lp, 4), "iv": round(iv_lp, 4), "theoretical": theo_lp},
            {"leg": "Short Put", "strike": sp, "exp": exp, "price": round(p_sp, 4), "iv": round(iv_sp, 4), "theoretical": theo_sp},
            {"leg": "Short Call", "strike": sc, "exp": exp, "price": round(p_sc, 4), "iv": round(iv_sc, 4), "theoretical": theo_sc},
            {"leg": "Long Call", "strike": lc, "exp": exp, "price": round(p_lc, 4), "iv": round(iv_lc, 4), "theoretical": theo_lc},
        ]

    elif body.strategy == "double_calendar":
        ps = float(legs.get("putStrike") or legs.get("put_strike", 0))
        cs = float(legs.get("callStrike") or legs.get("call_strike", 0))
        front_exp = str(legs.get("frontExpiration") or legs.get("front_expiration", ""))
        back_exp = str(legs.get("backExpiration") or legs.get("back_expiration", ""))

        if not all([ps, cs, front_exp, back_exp]):
            raise HTTPException(422, "Both strikes and both expirations required")

        T_front = _tte(front_exp)
        T_back = _tte(back_exp)

        p_fp, iv_fp, theo_fp = _price_or_bs(ps, T_front, False, front_exp)
        p_bp, iv_bp, theo_bp = _price_or_bs(ps, T_back, False, back_exp)
        p_fc, iv_fc, theo_fc = _price_or_bs(cs, T_front, True, front_exp)
        p_bc, iv_bc, theo_bc = _price_or_bs(cs, T_back, True, back_exp)

        entry_cost = p_bp + p_bc - p_fp - p_fc
        net_debit = entry_cost * 100 * n

        g_fp = _bs_greeks(S, ps, T_front, r, iv_fp, False)
        g_bp = _bs_greeks(S, ps, T_back, r, iv_bp, False)
        g_fc = _bs_greeks(S, cs, T_front, r, iv_fc, True)
        g_bc = _bs_greeks(S, cs, T_back, r, iv_bc, True)

        greeks = {
            k: round((-g_fp[k] + g_bp[k] - g_fc[k] + g_bc[k]) * n, 6)
            for k in ("delta", "gamma", "theta", "vega")
        }

        avg_sigma = sum([iv_fp, iv_bp, iv_fc, iv_bc]) / 4
        profile = _scan_pnl_profile(
            "double_calendar", S,
            {"ps": ps, "cs": cs},
            {"front": front_exp, "back": back_exp},
            r, avg_sigma, entry_cost, n,
        )

        leg_detail = [
            {"leg": "Short Front Put", "strike": ps, "exp": front_exp, "price": round(p_fp, 4), "iv": round(iv_fp, 4), "theoretical": theo_fp},
            {"leg": "Long Back Put", "strike": ps, "exp": back_exp, "price": round(p_bp, 4), "iv": round(iv_bp, 4), "theoretical": theo_bp},
            {"leg": "Short Front Call", "strike": cs, "exp": front_exp, "price": round(p_fc, 4), "iv": round(iv_fc, 4), "theoretical": theo_fc},
            {"leg": "Long Back Call", "strike": cs, "exp": back_exp, "price": round(p_bc, 4), "iv": round(iv_bc, 4), "theoretical": theo_bc},
        ]
    else:
        raise HTTPException(400, f"Unknown strategy: {body.strategy}")

    # Compute average IV across legs
    avg_iv = None
    if leg_detail:
        ivs = [leg["iv"] for leg in leg_detail if leg.get("iv") and leg["iv"] > 0]
        avg_iv = round(sum(ivs) / len(ivs), 4) if ivs else None

    return {
        "symbol": body.symbol,
        "strategy": body.strategy,
        "contracts": n,
        "net_debit": round(net_debit, 2),
        "max_profit": profile["max_profit"],
        "max_loss": profile["max_loss"],
        "lower_breakeven": profile["lower_breakeven"],
        "upper_breakeven": profile["upper_breakeven"],
        "probability_of_profit": profile["probability_of_profit"],
        "greeks": greeks,
        "pnl_curve": profile["pnl_curve"],
        "legs": leg_detail,
        "implied_vol": avg_iv,
        "pricing_mode": "chain" if body.use_chain_prices and chain_opts else "black_scholes",
        "risk_free_rate": r,
    }


# ---------------------------------------------------------------------------
# 7. Alerts — in-memory store with create/list/trigger/delete
# ---------------------------------------------------------------------------

_alerts: list[dict] = []
_alert_id_seq = 0


class AlertCreate(BaseModel):
    price: float
    condition: str = "above"  # "above" | "below"
    label: str = ""


@router.get("/alerts")
async def get_alerts():
    return {"alerts": _alerts}


@router.post("/alerts")
async def create_alert(body: AlertCreate):
    global _alert_id_seq
    _alert_id_seq += 1
    alert = {
        "id": _alert_id_seq,
        "price": body.price,
        "condition": body.condition,
        "label": body.label or f"Price {body.condition} {body.price}",
        "triggered": False,
        "created_at": _now_ct().isoformat(),
    }
    _alerts.append(alert)
    return alert


@router.post("/alerts/{alert_id}/trigger")
async def trigger_alert(alert_id: int):
    for a in _alerts:
        if a["id"] == alert_id:
            a["triggered"] = True
            return {"ok": True}
    raise HTTPException(404, "Alert not found")


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: int):
    global _alerts
    before = len(_alerts)
    _alerts = [a for a in _alerts if a["id"] != alert_id]
    if len(_alerts) == before:
        raise HTTPException(404, "Alert not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 8. Positions — Postgres-backed spread position tracker
# ---------------------------------------------------------------------------

MAX_OPEN_POSITIONS = 10

def _discord_url() -> str:
    return os.getenv("DISCORD_WEBHOOK_URL", "")

def _anthropic_key() -> str:
    return os.getenv("ANTHROPIC_API_KEY", "")

STRATEGY_LABELS = {
    "double_diagonal": "Double Diagonal",
    "double_calendar": "Double Calendar",
    "iron_condor": "Iron Condor",
}


def _pos_to_dict(pos: Position) -> dict:
    """Serialize a Position ORM object to a JSON-friendly dict."""
    today = _today_ct()
    dte = (pos.short_exp - today).days if pos.short_exp else None
    return {
        "id": pos.id,
        "symbol": pos.symbol,
        "strategy": pos.strategy,
        "label": pos.label or "",
        "long_put": pos.long_put,
        "short_put": pos.short_put,
        "short_call": pos.short_call,
        "long_call": pos.long_call,
        "short_exp": pos.short_exp.isoformat() if pos.short_exp else None,
        "long_exp": pos.long_exp.isoformat() if pos.long_exp else None,
        "contracts": pos.contracts,
        "entry_credit": pos.entry_credit,
        "entry_price": pos.entry_price,
        "entry_date": pos.entry_date.isoformat() if pos.entry_date else None,
        "entry_spot": pos.entry_spot,
        "max_profit": pos.max_profit,
        "max_loss": pos.max_loss,
        "breakeven_low": pos.breakeven_low,
        "breakeven_high": pos.breakeven_high,
        "notes": pos.notes or "",
        "status": pos.status,
        "close_date": pos.close_date.isoformat() if pos.close_date else None,
        "close_price": pos.close_price,
        "realized_pnl": pos.realized_pnl,
        "dte": dte,
    }


def _mark_to_dict(m: DailyMark) -> dict:
    return {
        "id": m.id,
        "position_id": m.position_id,
        "mark_date": m.mark_date.isoformat() if m.mark_date else None,
        "current_value": m.current_value,
        "unrealized_pnl": m.unrealized_pnl,
        "spot_price": m.spot_price,
        "dte": m.dte,
        "iv": m.iv,
    }


def _strikes_str(pos: Position) -> str:
    """Format strikes as '550/555/580/585'."""
    return f"{pos.long_put}/{pos.short_put}/{pos.short_call}/{pos.long_call}"


class PositionCreate(BaseModel):
    symbol: str = "SPY"
    strategy: str
    label: str = ""
    long_put: float
    short_put: float
    short_call: float
    long_call: float
    short_exp: str  # YYYY-MM-DD
    long_exp: str | None = None
    contracts: int = 1
    entry_credit: float  # total credit ($)
    entry_price: float  # per-contract credit
    entry_spot: float | None = None
    max_profit: float | None = None
    max_loss: float | None = None
    breakeven_low: float | None = None
    breakeven_high: float | None = None
    notes: str = ""


class PositionUpdate(BaseModel):
    label: str | None = None
    notes: str | None = None
    contracts: int | None = None


class PositionCloseBody(BaseModel):
    close_price: float  # per-contract debit to close


# --- GET /positions?status=open|closed|all ---
@router.get("/positions")
async def get_positions(status: str = "open", db: Session = Depends(get_db)):
    try:
        q = db.query(Position)
        if status in ("open", "closed"):
            q = q.filter(Position.status == status)
        positions = q.order_by(Position.entry_date.desc()).all()
        return {"positions": [_pos_to_dict(p) for p in positions]}
    except Exception as e:
        logger.error(f"get_positions DB error: {e}")
        return {"positions": [], "error": f"Database unavailable: {e}"}


# --- POST /positions (10-slot enforcement) ---
@router.post("/positions")
async def create_position(body: PositionCreate, db: Session = Depends(get_db)):
    try:
        open_count = db.query(Position).filter(Position.status == "open").count()
    except Exception as e:
        logger.error(f"DB query failed in create_position: {e}")
        raise HTTPException(500, f"Database error: {e}")

    if open_count >= MAX_OPEN_POSITIONS:
        raise HTTPException(400, "Maximum 10 open positions reached.")

    try:
        short_exp_date = datetime.strptime(body.short_exp, "%Y-%m-%d").date()
    except (ValueError, TypeError) as e:
        raise HTTPException(422, f"Invalid short_exp date '{body.short_exp}': {e}")
    long_exp_date = None
    if body.long_exp:
        try:
            long_exp_date = datetime.strptime(body.long_exp, "%Y-%m-%d").date()
        except (ValueError, TypeError) as e:
            raise HTTPException(422, f"Invalid long_exp date '{body.long_exp}': {e}")

    try:
        pos = Position(
            symbol=body.symbol,
            strategy=body.strategy,
            label=body.label,
            long_put=body.long_put,
            short_put=body.short_put,
            short_call=body.short_call,
            long_call=body.long_call,
            short_exp=short_exp_date,
            long_exp=long_exp_date,
            contracts=body.contracts,
            entry_credit=body.entry_credit,
            entry_price=body.entry_price,
            entry_spot=body.entry_spot,
            max_profit=body.max_profit,
            max_loss=body.max_loss,
            breakeven_low=body.breakeven_low,
            breakeven_high=body.breakeven_high,
            notes=body.notes,
            status="open",
        )
        db.add(pos)
        db.commit()
        db.refresh(pos)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save position: {e}")
        raise HTTPException(500, f"Failed to save position: {e}")
    return _pos_to_dict(pos)


# --- GET /positions/summary (portfolio roll-up) ---
# NOTE: must be defined BEFORE /positions/{position_id} to avoid path conflict
@router.get("/positions/summary")
async def positions_summary(request: Request, db: Session = Depends(get_db)):
    open_positions = db.query(Position).filter(Position.status == "open").all()
    closed_positions = db.query(Position).filter(Position.status == "closed").all()

    total_credit = sum(p.entry_credit for p in open_positions)
    total_realized = sum(p.realized_pnl or 0 for p in closed_positions)
    slots_used = len(open_positions)

    # Try to get live unrealised P&L for open positions via last marks
    total_unrealized = 0.0
    for p in open_positions:
        latest_mark = (
            db.query(DailyMark)
            .filter(DailyMark.position_id == p.id)
            .order_by(DailyMark.mark_date.desc())
            .first()
        )
        if latest_mark and latest_mark.unrealized_pnl is not None:
            total_unrealized += latest_mark.unrealized_pnl

    return {
        "slots_used": slots_used,
        "slots_total": MAX_OPEN_POSITIONS,
        "total_credit": round(total_credit, 2),
        "total_unrealized": round(total_unrealized, 2),
        "total_realized": round(total_realized, 2),
        "open_count": slots_used,
        "closed_count": len(closed_positions),
    }


# --- GET /positions/{id} (with mark history) ---
@router.get("/positions/{position_id}")
async def get_position(position_id: int, db: Session = Depends(get_db)):
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(404, "Position not found")
    result = _pos_to_dict(pos)
    result["marks"] = [_mark_to_dict(m) for m in pos.marks]
    return result


# --- PATCH /positions/{id} (update label/notes/contracts) ---
@router.patch("/positions/{position_id}")
async def update_position(
    position_id: int, body: PositionUpdate, db: Session = Depends(get_db)
):
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(404, "Position not found")
    if body.label is not None:
        pos.label = body.label
    if body.notes is not None:
        pos.notes = body.notes
    if body.contracts is not None:
        pos.contracts = body.contracts
    db.commit()
    db.refresh(pos)
    return _pos_to_dict(pos)


# --- POST /positions/{id}/close ---
@router.post("/positions/{position_id}/close")
async def close_position(
    position_id: int, body: PositionCloseBody, db: Session = Depends(get_db)
):
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(404, "Position not found")
    if pos.status == "closed":
        raise HTTPException(409, "Position already closed")

    realized = round((pos.entry_price - body.close_price) * 100 * pos.contracts, 2)

    pos.status = "closed"
    pos.close_date = _today_ct()
    pos.close_price = body.close_price
    pos.realized_pnl = realized
    db.commit()
    db.refresh(pos)

    # Trigger Discord closed-position post
    _discord_post_closed(pos)

    return _pos_to_dict(pos)


# --- DELETE /positions/{id} ---
@router.delete("/positions/{position_id}")
async def delete_position(position_id: int, db: Session = Depends(get_db)):
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(404, "Position not found")
    db.delete(pos)
    db.commit()
    return {"ok": True}


# --- GET /positions/{id}/pnl (live unrealised P&L) ---
@router.get("/positions/{position_id}/pnl")
async def position_live_pnl(
    request: Request, position_id: int, db: Session = Depends(get_db)
):
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(404, "Position not found")

    # Get current spot price
    q = await _get_quote(request, pos.symbol)
    current_price = q.get("last")

    # Try to get current spread value via BS repricing
    current_value = None
    unrealized_pnl = None
    pnl_pct = None

    if current_price:
        r, sigma = RISK_FREE_RATE, 0.20
        today_date = _today_ct()

        def tte(d):
            return max((d - today_date).days, 0) / 365.0 if d else 0

        if pos.strategy == "double_diagonal" and pos.long_exp:
            T_short = tte(pos.short_exp)
            T_long = tte(pos.long_exp)
            val = (
                _bs_price(current_price, pos.short_put, T_short, r, sigma, False)
                + _bs_price(current_price, pos.short_call, T_short, r, sigma, True)
                - _bs_price(current_price, pos.long_put, T_long, r, sigma, False)
                - _bs_price(current_price, pos.long_call, T_long, r, sigma, True)
            )
        elif pos.strategy == "double_calendar" and pos.long_exp:
            T_front = tte(pos.short_exp)
            T_back = tte(pos.long_exp)
            val = (
                _bs_price(current_price, pos.short_put, T_front, r, sigma, False)
                + _bs_price(current_price, pos.short_call, T_front, r, sigma, True)
                - _bs_price(current_price, pos.long_put, T_back, r, sigma, False)
                - _bs_price(current_price, pos.long_call, T_back, r, sigma, True)
            )
        else:  # iron_condor — single expiration
            T = tte(pos.short_exp)
            val = (
                _bs_price(current_price, pos.short_put, T, r, sigma, False)
                + _bs_price(current_price, pos.short_call, T, r, sigma, True)
                - _bs_price(current_price, pos.long_put, T, r, sigma, False)
                - _bs_price(current_price, pos.long_call, T, r, sigma, True)
            )

        current_value = round(val, 4)  # per-contract value to close
        unrealized_pnl = round((pos.entry_price - val) * 100 * pos.contracts, 2)
        if pos.max_profit and pos.max_profit != 0:
            pnl_pct = round(unrealized_pnl / abs(pos.max_profit) * 100, 2)

    # Also include latest mark as fallback
    latest_mark = (
        db.query(DailyMark)
        .filter(DailyMark.position_id == pos.id)
        .order_by(DailyMark.mark_date.desc())
        .first()
    )

    return {
        "position_id": position_id,
        "current_price": current_price,
        "current_value": current_value,
        "unrealized_pnl": unrealized_pnl,
        "pnl_pct": pnl_pct,
        "entry_credit": pos.entry_credit,
        "entry_price": pos.entry_price,
        "max_profit": pos.max_profit,
        "last_mark": _mark_to_dict(latest_mark) if latest_mark else None,
    }


# --- POST /positions/mark (EOD mark all open positions) ---
@router.post("/positions/mark")
async def mark_all_positions(request: Request, db: Session = Depends(get_db)):
    open_positions = db.query(Position).filter(Position.status == "open").all()
    if not open_positions:
        return {"marked": 0}

    q = await _get_quote(request, "SPY")
    current_price = q.get("last")
    if not current_price:
        raise HTTPException(502, "Could not fetch current price for marking")

    today_date = _today_ct()
    r, sigma = 0.05, 0.20
    marked = 0

    for pos in open_positions:
        try:
            def tte(d):
                return max((d - today_date).days, 0) / 365.0 if d else 0

            if pos.strategy == "double_diagonal" and pos.long_exp:
                T_short = tte(pos.short_exp)
                T_long = tte(pos.long_exp)
                val = (
                    _bs_price(current_price, pos.short_put, T_short, r, sigma, False)
                    + _bs_price(current_price, pos.short_call, T_short, r, sigma, True)
                    - _bs_price(current_price, pos.long_put, T_long, r, sigma, False)
                    - _bs_price(current_price, pos.long_call, T_long, r, sigma, True)
                )
            elif pos.strategy == "double_calendar" and pos.long_exp:
                T_front = tte(pos.short_exp)
                T_back = tte(pos.long_exp)
                val = (
                    _bs_price(current_price, pos.short_put, T_front, r, sigma, False)
                    + _bs_price(current_price, pos.short_call, T_front, r, sigma, True)
                    - _bs_price(current_price, pos.long_put, T_back, r, sigma, False)
                    - _bs_price(current_price, pos.long_call, T_back, r, sigma, True)
                )
            else:
                T = tte(pos.short_exp)
                val = (
                    _bs_price(current_price, pos.short_put, T, r, sigma, False)
                    + _bs_price(current_price, pos.short_call, T, r, sigma, True)
                    - _bs_price(current_price, pos.long_put, T, r, sigma, False)
                    - _bs_price(current_price, pos.long_call, T, r, sigma, True)
                )

            dte_val = (pos.short_exp - today_date).days if pos.short_exp else None
            unrealized = round((pos.entry_price - val) * 100 * pos.contracts, 2)

            mark = DailyMark(
                position_id=pos.id,
                mark_date=today_date,
                current_value=round(val, 4),
                unrealized_pnl=unrealized,
                spot_price=current_price,
                dte=dte_val,
            )
            db.merge(mark)  # upsert — UNIQUE(position_id, mark_date)
            marked += 1
        except Exception:
            # Mark with NULL values if pricing fails
            mark = DailyMark(
                position_id=pos.id,
                mark_date=today_date,
                spot_price=current_price,
            )
            db.merge(mark)

    db.commit()
    return {"marked": marked, "spot_price": current_price}


# ---------------------------------------------------------------------------
# 9. Discord webhook posting for positions
# ---------------------------------------------------------------------------

def _generate_payoff_chart(
    curve: list[dict],
    spot_price: float | None = None,
    breakevens: dict | None = None,
    max_profit: float | None = None,
    max_loss: float | None = None,
    title: str = "",
) -> bytes | None:
    """Generate a payoff chart PNG and return as bytes."""
    try:
        import io
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker

        if not curve or len(curve) < 2:
            return None

        prices = [p["price"] for p in curve]
        pnls = [p["pnl"] for p in curve]

        fig, ax = plt.subplots(figsize=(7, 3.5), dpi=150)
        fig.patch.set_facecolor("#0d0d18")
        ax.set_facecolor("#0d0d18")

        # Fill profit/loss zones
        ax.fill_between(prices, pnls, 0, where=[p >= 0 for p in pnls],
                         color="#00e676", alpha=0.15, interpolate=True)
        ax.fill_between(prices, pnls, 0, where=[p <= 0 for p in pnls],
                         color="#ff1744", alpha=0.12, interpolate=True)

        # Main P&L line
        ax.plot(prices, pnls, color="#3b82f6", linewidth=2, zorder=5)

        # Zero line
        ax.axhline(y=0, color="#475569", linewidth=0.7, linestyle="--", zorder=3)

        # Spot price
        if spot_price and min(prices) <= spot_price <= max(prices):
            ax.axvline(x=spot_price, color="#facc15", linewidth=1, linestyle="--",
                       alpha=0.8, zorder=4)
            ax.text(spot_price, max(pnls) * 0.92, f" Spot ${spot_price:.0f}",
                    color="#facc15", fontsize=8, fontfamily="monospace", zorder=6)

        # Breakevens
        if breakevens:
            for be_val in [breakevens.get("lower"), breakevens.get("upper")]:
                if be_val and min(prices) <= be_val <= max(prices):
                    ax.axvline(x=be_val, color="#a78bfa", linewidth=1,
                               linestyle=":", alpha=0.7, zorder=4)
                    ax.text(be_val, min(pnls) * 0.85, f" BE ${be_val:.0f}",
                            color="#a78bfa", fontsize=7, fontfamily="monospace", zorder=6)

        # Max profit / loss annotations
        if max_profit is not None:
            ax.text(0.98, 0.95, f"Max Profit: +${max_profit:,.0f}",
                    transform=ax.transAxes, color="#00e676", fontsize=8,
                    fontfamily="monospace", ha="right", va="top", zorder=6)
        if max_loss is not None:
            ax.text(0.98, 0.05, f"Max Loss: ${max_loss:,.0f}",
                    transform=ax.transAxes, color="#ff5252", fontsize=8,
                    fontfamily="monospace", ha="right", va="bottom", zorder=6)

        # Styling
        ax.set_xlabel("Underlying Price", color="#888", fontsize=9, fontfamily="monospace")
        ax.set_ylabel("P&L ($)", color="#888", fontsize=9, fontfamily="monospace")
        if title:
            ax.set_title(title, color="#fff", fontsize=11, fontfamily="monospace",
                         fontweight="bold", pad=10)
        ax.tick_params(colors="#555", labelsize=8)
        ax.xaxis.set_major_formatter(ticker.FormatStrFormatter("$%.0f"))
        ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("$%.0f"))
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color("#1a1a2e")
        ax.spines["left"].set_color("#1a1a2e")
        ax.grid(axis="y", color="#1a1a2e", linewidth=0.5, alpha=0.5)

        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor="#0d0d18", edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        logger.error(f"[Discord] Chart generation failed: {e}")
        return None


def _send_discord_embed(embed: dict, image_bytes: bytes | None = None) -> bool:
    """Send an embed to Discord webhook, optionally with an attached chart image."""
    import requests as req

    url = _discord_url()
    if not url:
        logger.warning("[Discord] DISCORD_WEBHOOK_URL not set — skipping post")
        return False
    try:
        if image_bytes:
            # Multipart upload: embed as JSON payload + image as file attachment
            embed_copy = {**embed, "image": {"url": "attachment://payoff.png"}}
            payload = json.dumps({"embeds": [embed_copy]})
            resp = req.post(
                url,
                data={"payload_json": payload},
                files=[("files[0]", ("payoff.png", image_bytes, "image/png"))],
                timeout=15,
            )
            # If multipart fails, fall back to embed-only (no chart)
            if resp.status_code not in (200, 204):
                logger.warning(f"[Discord] Multipart failed ({resp.status_code}), retrying embed-only")
                resp = req.post(
                    url,
                    json={"embeds": [embed]},
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                )
        else:
            resp = req.post(
                url,
                json={"embeds": [embed]},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
        if resp.status_code in (200, 204):
            logger.info(f"[Discord] Embed posted successfully: {embed.get('title', '?')}")
            return True
        logger.error(f"[Discord] Post failed: {resp.status_code} {resp.text[:300]}")
        return False
    except Exception as e:
        logger.error(f"[Discord] Post exception: {e}")
        return False


def _discord_post_closed(pos: Position):
    """Post closed-position embed to Discord. Called automatically on close."""
    strat_label = STRATEGY_LABELS.get(pos.strategy, pos.strategy)
    pnl = pos.realized_pnl or 0
    days_held = (pos.close_date - pos.entry_date).days if pos.close_date and pos.entry_date else 0
    pct_of_max = round(pnl / abs(pos.max_profit) * 100, 1) if pos.max_profit else 0

    if pnl >= 0:
        color = 0x00E676
        footer_msg = "Well done. Protect the gains."
    else:
        color = 0xFF1744
        footer_msg = "Cut clean. Next setup is coming. Stay the course."

    embed = {
        "title": f"\u2705 POSITION CLOSED \u00b7 {pos.symbol} {strat_label}",
        "color": color,
        "fields": [
            {"name": "Entry", "value": f"+${pos.entry_credit:,.2f}", "inline": True},
            {"name": "Exit", "value": f"-${(pos.close_price or 0) * 100 * pos.contracts:,.2f}", "inline": True},
            {"name": "Realized P&L", "value": f"${pnl:+,.2f} ({pct_of_max:+.1f}% of max profit)", "inline": False},
            {"name": "Held", "value": f"{days_held} days \u00b7 {pos.entry_date} \u2192 {pos.close_date}", "inline": False},
        ],
        "footer": {"text": footer_msg},
        "timestamp": _now_ct().isoformat(),
    }
    _send_discord_embed(embed)


class DiscordPushSpread(BaseModel):
    symbol: str = "SPY"
    strategy: str = ""
    spot: float | None = None
    legs: dict = {}
    short_exp: str = ""
    long_exp: str = ""
    net_credit: float | None = None
    max_profit: float | None = None
    max_loss: float | None = None
    breakevens: list[float] = []
    chance_of_profit: float | None = None
    implied_vol: float | None = None
    contracts: int = 1
    gex_suggestion: str = ""
    pricing_mode: str = ""
    pnl_curve: list[dict] = []


@router.post("/discord/test")
async def discord_test():
    """Test Discord webhook connectivity — posts a minimal embed, no chart."""
    url = _discord_url()
    webhook_set = bool(url)
    if not webhook_set:
        return {"webhook_set": False, "status_code": None, "success": False,
                "detail": "DISCORD_WEBHOOK_URL not set"}

    import requests as req
    embed = {
        "title": "SpreadWorks — Webhook Test",
        "description": "If you see this, the webhook is working.",
        "color": 0x3B82F6,
        "footer": {"text": "SpreadWorks · Test Ping"},
        "timestamp": _now_ct().isoformat(),
    }
    try:
        resp = req.post(url, json={"embeds": [embed]},
                        headers={"Content-Type": "application/json"}, timeout=10)
        return {"webhook_set": True, "status_code": resp.status_code,
                "success": resp.status_code in (200, 204)}
    except Exception as e:
        return {"webhook_set": True, "status_code": None, "success": False,
                "detail": str(e)}


@router.post("/discord/test-daily")
async def discord_test_daily():
    """Fire all 3 rich daily posts (market open, economic, market close) immediately for testing."""
    import time as _time

    try:
        from .verses import VERSES
        from .tips import TIPS
        from .close_messages import CLOSE_MESSAGES
        from .economic_events import (
            get_central_now, get_todays_events, get_upcoming_events,
            format_countdown, format_event_time,
        )
    except ImportError as e:
        raise HTTPException(500, f"Content modules not loaded: {e}")

    results = {}
    now = get_central_now()

    def _impact_color(impact: str) -> int:
        return {"HIGH": 0xFF1744, "MEDIUM": 0xFFD600, "LOW": 0x448AFF}.get(impact, 0x448AFF)

    def _rotation_index(items, offset=0) -> int:
        day_of_year = now.timetuple().tm_yday
        return (day_of_year + offset) % len(items)

    # 1) Market Open — Bible verse + tip
    verse = VERSES[_rotation_index(VERSES)]
    tip = TIPS[_rotation_index(TIPS, offset=37)]
    embed_open = {
        "title": "\U0001f305 MARKET OPENS IN 30 MINUTES",
        "color": 0x00E676,
        "fields": [
            {"name": f"\U0001f4d6 {verse['reference']}", "value": f"*\"{verse['text']}\"*", "inline": False},
            {"name": "\U0001f4ca SPREAD TRADER TIP", "value": tip, "inline": False},
        ],
        "footer": {"text": f"SpreadWorks \u2022 {now.strftime('%A, %B %d, %Y')} \u2022 Good luck today. Trade with discipline."},
        "timestamp": now.isoformat(),
    }
    results["market_open"] = _send_discord_embed(embed_open)
    _time.sleep(1)

    # 2) Economic countdown
    today_date = now.date()
    todays_events = get_todays_events(today_date)
    if todays_events:
        for event in todays_events:
            event_time = format_event_time(event["datetime"])
            embed_econ = {
                "title": "\u26a1 ECONOMIC EVENT TODAY",
                "color": _impact_color(event["impact"]),
                "fields": [
                    {"name": f"\U0001f4c5 {event['name']}", "value": f"**{event_time}**\n{event['description']}", "inline": False},
                    {"name": f"Impact: **{event['impact']}**", "value": "\U0001f4a1 Consider closing or hedging positions before this event.", "inline": False},
                ],
                "footer": {"text": f"SpreadWorks \u2022 {now.strftime('%A, %B %d, %Y')}"},
                "timestamp": now.isoformat(),
            }
            _send_discord_embed(embed_econ)
        results["economic"] = True
    else:
        upcoming = get_upcoming_events(days=7, count=3)
        if upcoming:
            fields = []
            for event in upcoming:
                countdown = format_countdown(event["datetime"])
                event_time = format_event_time(event["datetime"])
                fields.append({
                    "name": f"\U0001f4c5 {event['name']}",
                    "value": f"\U0001f4c6 {event['datetime'].strftime('%A, %b %-d')} at {event_time}\n\u23f3 **{countdown}**\nImpact: **{event['impact']}**",
                    "inline": False,
                })
            embed_econ = {
                "title": "\U0001f4c5 NEXT MAJOR ECONOMIC EVENTS",
                "color": _impact_color(upcoming[0]["impact"]),
                "fields": fields,
                "footer": {"text": f"SpreadWorks \u2022 {now.strftime('%A, %B %d, %Y')}"},
                "timestamp": now.isoformat(),
            }
            results["economic"] = _send_discord_embed(embed_econ)
        else:
            results["economic"] = "no_events_within_7_days"
    _time.sleep(1)

    # 3) Market Close — reflection
    close_msg = CLOSE_MESSAGES[_rotation_index(CLOSE_MESSAGES, offset=71)]
    embed_close = {
        "title": "\U0001f514 MARKET CLOSED",
        "color": 0x448AFF,
        "fields": [
            {"name": "\U0001f4ad Closing Thought", "value": close_msg, "inline": False},
            {"name": "\U0001f4cb End of Day Checklist", "value": "\u2022 Review your positions and open orders\n\u2022 Log your trades in your journal\n\u2022 Check tomorrow's economic calendar\n\u2022 Set alerts for key levels\n\u2022 Rest well \u2014 tomorrow is a new day", "inline": False},
        ],
        "footer": {"text": f"SpreadWorks \u2022 {now.strftime('%A, %B %d, %Y')} \u2022 Rest up. Trade tomorrow."},
        "timestamp": now.isoformat(),
    }
    results["market_close"] = _send_discord_embed(embed_close)

    return {"posted": results, "verse": verse["reference"], "tip_index": _rotation_index(TIPS, offset=37)}


@router.post("/discord/push-spread")
async def discord_push_spread(body: DiscordPushSpread):
    """Push current spread analysis to Discord as a rich embed."""
    if not _discord_url():
        raise HTTPException(503, "DISCORD_WEBHOOK_URL not configured")

    strat_label = STRATEGY_LABELS.get(body.strategy, body.strategy or "Spread")
    is_credit = body.net_credit is not None and body.net_credit > 0
    color = 0x00E676 if is_credit else 0xFF1744

    legs = body.legs
    legs_str = (
        f"LP {legs.get('long_put', '?')} / SP {legs.get('short_put', '?')} / "
        f"SC {legs.get('short_call', '?')} / LC {legs.get('long_call', '?')}"
    )

    be_str = " / ".join(f"${b:.2f}" for b in body.breakevens) if body.breakevens else "--"
    iv_str = f"{body.implied_vol:.1f}%" if body.implied_vol else "--"
    cop_str = f"{body.chance_of_profit:.1f}%" if body.chance_of_profit else "--"
    credit_str = f"+${body.net_credit:,.0f}" if body.net_credit and body.net_credit > 0 else f"-${abs(body.net_credit or 0):,.0f}"
    pricing_note = " (theoretical)" if body.pricing_mode == "black_scholes" else ""

    footer_source = "GEX Suggest" if body.gex_suggestion else "Manual"

    fields = [
        {"name": "Legs", "value": legs_str, "inline": False},
        {"name": "Short Exp", "value": body.short_exp or "--", "inline": True},
        {"name": "Long Exp", "value": body.long_exp or "--", "inline": True},
        {"name": "Net Credit", "value": f"{credit_str}{pricing_note}", "inline": True},
        {"name": "Max Profit", "value": f"${body.max_profit:,.0f}" if body.max_profit else "--", "inline": True},
        {"name": "Max Loss", "value": f"${body.max_loss:,.0f}" if body.max_loss else "--", "inline": True},
        {"name": "COP", "value": cop_str, "inline": True},
        {"name": "Breakevens", "value": be_str, "inline": True},
        {"name": "IV", "value": iv_str, "inline": True},
        {"name": "Contracts", "value": str(body.contracts), "inline": True},
    ]

    if body.gex_suggestion:
        fields.append({"name": "GEX Signal", "value": body.gex_suggestion[:1024], "inline": False})

    embed = {
        "title": f"\U0001f4ca {body.symbol} {strat_label} \u00b7 Spot ${body.spot:,.2f}" if body.spot else f"\U0001f4ca {body.symbol} {strat_label}",
        "color": color,
        "fields": fields,
        "footer": {"text": f"SpreadWorks \u00b7 {footer_source}"},
        "timestamp": _now_ct().isoformat(),
    }

    # Generate payoff chart if curve data provided
    chart_bytes = None
    if body.pnl_curve:
        be_dict = None
        if body.breakevens:
            be_dict = {
                "lower": body.breakevens[0] if len(body.breakevens) > 0 else None,
                "upper": body.breakevens[1] if len(body.breakevens) > 1 else None,
            }
        chart_title = f"{body.symbol} {strat_label}"
        if body.spot:
            chart_title += f" \u00b7 Spot ${body.spot:,.2f}"
        chart_bytes = _generate_payoff_chart(
            curve=body.pnl_curve,
            spot_price=body.spot,
            breakevens=be_dict,
            max_profit=body.max_profit,
            max_loss=body.max_loss,
            title=chart_title,
        )

    ok = _send_discord_embed(embed, image_bytes=chart_bytes)
    if not ok:
        raise HTTPException(502, "Failed to post to Discord")
    return {"posted": True}


@router.post("/discord/post-open")
async def discord_post_open(db: Session = Depends(get_db)):
    """Post open positions summary to Discord (like morning post)."""
    open_positions = db.query(Position).filter(Position.status == "open").all()
    if not open_positions:
        return {"posted": False, "reason": "No open positions"}

    today_str = _today_ct().strftime("%B %d, %Y")
    total_credit = sum(p.entry_credit for p in open_positions)

    lines = []
    for pos in open_positions:
        strat_label = STRATEGY_LABELS.get(pos.strategy, pos.strategy)
        dte = (pos.short_exp - _today_ct()).days if pos.short_exp else "?"
        lines.append(
            f"{pos.symbol} {strat_label} \u00b7 {_strikes_str(pos)} \u00b7 "
            f"Entry: +${pos.entry_credit:,.2f}\n"
            f"Max Profit: ${pos.max_profit:,.2f} | Max Loss: ${pos.max_loss:,.2f} | {dte}DTE"
            if pos.max_profit is not None and pos.max_loss is not None
            else f"{pos.symbol} {strat_label} \u00b7 {_strikes_str(pos)} \u00b7 "
                 f"Entry: +${pos.entry_credit:,.2f} | {dte}DTE"
        )

    positions_text = "\n\n".join(lines)

    embed = {
        "title": f"\U0001f4cb TODAY'S OPEN SPREADS \u00b7 {today_str}",
        "color": 0x448AFF,
        "description": positions_text,
        "fields": [
            {"name": "Total Credit", "value": f"+${total_credit:,.2f}", "inline": True},
            {"name": "Positions", "value": f"{len(open_positions)} active", "inline": True},
        ],
        "footer": {"text": "Trade with discipline \U0001f64f"},
        "timestamp": _now_ct().isoformat(),
    }

    ok = _send_discord_embed(embed)
    return {"posted": ok, "positions": len(open_positions)}


@router.post("/discord/post-eod")
async def discord_post_eod(request: Request, db: Session = Depends(get_db)):
    """Post end-of-day summary to Discord with Claude AI commentary."""
    open_positions = db.query(Position).filter(Position.status == "open").all()
    if not open_positions:
        return {"posted": False, "reason": "No open positions"}

    # Get current price
    q = await _get_quote(request, "SPY")
    current_price = q.get("last", 0)
    today_str = _today_ct().strftime("%B %d, %Y")
    today_date = _today_ct()

    # Build per-position P&L lines using latest marks
    lines = []
    total_unrealized = 0.0
    positions_for_ai = []

    for pos in open_positions:
        latest = (
            db.query(DailyMark)
            .filter(DailyMark.position_id == pos.id)
            .order_by(DailyMark.mark_date.desc())
            .first()
        )
        pnl = latest.unrealized_pnl if latest and latest.unrealized_pnl is not None else 0
        cur_val = latest.current_value if latest else None
        total_unrealized += pnl
        pct = round(pnl / abs(pos.max_profit) * 100, 1) if pos.max_profit else 0

        strat = STRATEGY_LABELS.get(pos.strategy, pos.strategy)
        arrow = "\u25b2" if pnl >= 0 else "\u25bc"
        sign = "+" if pnl >= 0 else ""

        lines.append(
            f"{pos.symbol} {strat}\n"
            f"P&L: {sign}${pnl:,.2f} ({arrow}{sign}{pct:.1f}%)\n"
            f"Current value: ${cur_val:,.4f} | Entry: ${pos.entry_price:,.2f}"
            if cur_val is not None
            else f"{pos.symbol} {strat}\n"
                 f"P&L: {sign}${pnl:,.2f} ({arrow}{sign}{pct:.1f}%)"
        )

        dte = (pos.short_exp - today_date).days if pos.short_exp else None
        positions_for_ai.append({
            "symbol": pos.symbol,
            "strategy": strat,
            "strikes": _strikes_str(pos),
            "entry_credit": pos.entry_credit,
            "unrealized_pnl": pnl,
            "dte": dte,
            "max_profit": pos.max_profit,
            "max_loss": pos.max_loss,
        })

    # Closed today
    closed_today = db.query(Position).filter(
        Position.status == "closed",
        Position.close_date == today_date,
    ).count()

    total_credit = sum(p.entry_credit for p in open_positions)
    pnl_pct = round(total_unrealized / total_credit * 100, 1) if total_credit else 0

    # Claude AI commentary
    commentary = ""
    if _anthropic_key():
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=_anthropic_key())
            prompt = (
                f"You are an options trading analyst reviewing end-of-day positions for a spread trader.\n\n"
                f"Today's date: {today_str}\n"
                f"SPY closed at: ${current_price:.2f}\n\n"
                f"Open positions:\n"
            )
            for p in positions_for_ai:
                prompt += (
                    f"- {p['symbol']} {p['strategy']} {p['strikes']}: "
                    f"entry +${p['entry_credit']:,.2f}, unrealized ${p['unrealized_pnl']:+,.2f}, "
                    f"{p['dte']}DTE, max profit ${p['max_profit']}, max loss ${p['max_loss']}\n"
                )
            prompt += (
                f"\nFor each position provide:\n"
                f"1. One sentence on how today's price action affected it\n"
                f"2. One actionable recommendation (close, hold, watch level, roll)\n"
                f"3. Any risk to watch (upcoming events, IV change, DTE pressure)\n\n"
                f"Keep it concise \u2014 2-3 sentences per position max. "
                f"End with a 1-sentence overall portfolio summary. "
                f"Tone: professional, direct, faith-informed (brief encouragement okay, not preachy)."
            )
            msg = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            commentary = msg.content[0].text
        except Exception:
            commentary = "AI commentary unavailable"

    positions_text = "\n\n".join(lines)

    pnl_color = 0x00E676 if total_unrealized >= 0 else 0xFF1744

    embed = {
        "title": f"\U0001f514 END OF DAY UPDATE \u00b7 {today_str}",
        "color": pnl_color,
        "description": positions_text,
        "fields": [
            {"name": "\u2501" * 20, "value": "\u200b", "inline": False},
            {
                "name": "Portfolio P&L Today",
                "value": f"{'+'if total_unrealized >= 0 else ''}${total_unrealized:,.2f} ({pnl_pct:+.1f}% of total credit)",
                "inline": True,
            },
            {"name": "Open", "value": str(len(open_positions)), "inline": True},
            {"name": "Closed Today", "value": str(closed_today), "inline": True},
        ],
        "footer": {"text": "SpreadWorks \u2022 End of Day"},
        "timestamp": _now_ct().isoformat(),
    }
    if commentary:
        embed["fields"].append({
            "name": "\U0001f916 AI RECAP",
            "value": commentary[:1024],  # Discord field limit
            "inline": False,
        })

    ok = _send_discord_embed(embed)
    return {
        "posted": ok,
        "positions": len(open_positions),
        "total_unrealized": round(total_unrealized, 2),
        "commentary_available": bool(commentary and commentary != "AI commentary unavailable"),
    }


@router.post("/discord/push-position/{position_id}")
async def discord_push_position(
    request: Request, position_id: int, db: Session = Depends(get_db)
):
    """Push a single position's current status snapshot to Discord."""
    if not _discord_url():
        raise HTTPException(503, "DISCORD_WEBHOOK_URL not configured")

    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(404, "Position not found")

    strat_label = STRATEGY_LABELS.get(pos.strategy, pos.strategy)
    strikes_str = _strikes_str(pos)
    dte = (pos.short_exp - _today_ct()).days if pos.short_exp else None
    is_open = pos.status == "open"

    # Get live P&L for open positions
    unrealized_pnl = 0.0
    current_value = None
    pnl_pct = 0.0
    spot = None

    if is_open:
        try:
            q = await _get_quote(request, pos.symbol)
            spot = q.get("last")
            if spot:
                r, sigma = RISK_FREE_RATE, 0.20
                today_date = _today_ct()

                def tte(d):
                    return max((d - today_date).days, 0) / 365.0 if d else 0

                if pos.strategy == "double_diagonal" and pos.long_exp:
                    T_short = tte(pos.short_exp)
                    T_long = tte(pos.long_exp)
                    val = (
                        _bs_price(spot, pos.short_put, T_short, r, sigma, False)
                        + _bs_price(spot, pos.short_call, T_short, r, sigma, True)
                        - _bs_price(spot, pos.long_put, T_long, r, sigma, False)
                        - _bs_price(spot, pos.long_call, T_long, r, sigma, True)
                    )
                elif pos.strategy == "double_calendar" and pos.long_exp:
                    T_front = tte(pos.short_exp)
                    T_back = tte(pos.long_exp)
                    val = (
                        _bs_price(spot, pos.short_put, T_front, r, sigma, False)
                        + _bs_price(spot, pos.short_call, T_front, r, sigma, True)
                        - _bs_price(spot, pos.long_put, T_back, r, sigma, False)
                        - _bs_price(spot, pos.long_call, T_back, r, sigma, True)
                    )
                else:
                    T = tte(pos.short_exp)
                    val = (
                        _bs_price(spot, pos.short_put, T, r, sigma, False)
                        + _bs_price(spot, pos.short_call, T, r, sigma, True)
                        - _bs_price(spot, pos.long_put, T, r, sigma, False)
                        - _bs_price(spot, pos.long_call, T, r, sigma, True)
                    )
                current_value = round(val, 4)
                unrealized_pnl = round((pos.entry_price - val) * 100 * pos.contracts, 2)
                if pos.max_profit and pos.max_profit != 0:
                    pnl_pct = round(unrealized_pnl / abs(pos.max_profit) * 100, 1)
        except Exception:
            pass

    # Determine P&L values for the embed
    if is_open:
        pnl_val = unrealized_pnl
        pnl_label = "Unrealized P&L"
    else:
        pnl_val = pos.realized_pnl or 0
        pnl_label = "Realized P&L"
        if pos.max_profit and pos.max_profit != 0:
            pnl_pct = round(pnl_val / abs(pos.max_profit) * 100, 1)

    color = 0x00E676 if pnl_val >= 0 else 0xFF1744
    status_emoji = "\U0001f7e2" if is_open else "\U0001f534"
    pnl_sign = "+" if pnl_val >= 0 else ""

    fields = [
        {
            "name": "Strikes",
            "value": f"LP `{pos.long_put}` \u00b7 SP `{pos.short_put}` \u00b7 SC `{pos.short_call}` \u00b7 LC `{pos.long_call}`",
            "inline": False,
        },
        {
            "name": "Short Exp",
            "value": str(pos.short_exp) if pos.short_exp else "--",
            "inline": True,
        },
    ]
    if pos.long_exp:
        fields.append({
            "name": "Long Exp",
            "value": str(pos.long_exp),
            "inline": True,
        })
    if dte is not None:
        fields.append({"name": "DTE", "value": str(dte), "inline": True})

    fields.append({
        "name": "Entry Credit",
        "value": f"+${pos.entry_credit:,.2f}",
        "inline": True,
    })
    if current_value is not None:
        fields.append({
            "name": "Current Value",
            "value": f"${current_value:,.4f}",
            "inline": True,
        })
    fields.append({
        "name": pnl_label,
        "value": f"{pnl_sign}${pnl_val:,.2f} ({pnl_sign}{pnl_pct:.1f}%)",
        "inline": True,
    })
    if pos.max_profit is not None:
        fields.append({
            "name": "Max Profit",
            "value": f"${pos.max_profit:,.2f}",
            "inline": True,
        })
    if pos.max_loss is not None:
        fields.append({
            "name": "Max Loss",
            "value": f"${pos.max_loss:,.2f}",
            "inline": True,
        })
    fields.append({
        "name": "Contracts",
        "value": str(pos.contracts),
        "inline": True,
    })

    title_label = pos.label or f"#{pos.id}"
    chart_title = f"{pos.symbol} {strat_label} \u00b7 {title_label}"
    embed = {
        "title": f"{status_emoji} {chart_title}",
        "color": color,
        "fields": fields,
        "footer": {"text": f"SpreadWorks \u00b7 Opened {pos.entry_date}"},
        "timestamp": _now_ct().isoformat(),
    }

    # Generate payoff chart image (non-fatal if it fails)
    chart_bytes = None
    try:
        chart_bytes = _generate_position_payoff_chart(pos, spot, chart_title)
    except Exception as e:
        logger.warning(f"[Discord] Chart generation failed for position {position_id}: {e}")

    ok = _send_discord_embed(embed, image_bytes=chart_bytes)
    if not ok:
        raise HTTPException(502, "Failed to post to Discord")
    return {"posted": True, "position_id": position_id}


def _generate_position_payoff_chart(pos: Position, spot: float | None, title: str) -> bytes | None:
    """Build payoff curve data from a Position and render chart PNG."""
    lp, sp = pos.long_put, pos.short_put
    sc, lc = pos.short_call, pos.long_call
    entry = pos.entry_price
    n = pos.contracts
    sigma = 0.20
    r = RISK_FREE_RATE
    today_date = _today_ct()

    if pos.strategy in ("double_diagonal", "double_calendar") and pos.long_exp:
        if pos.strategy == "double_diagonal":
            profile = _scan_pnl_profile(
                "double_diagonal", spot or ((sp + sc) / 2),
                {"lp": lp, "sp": sp, "sc": sc, "lc": lc},
                {"short": str(pos.short_exp), "long": str(pos.long_exp)},
                r, sigma, entry, n,
            )
        else:
            profile = _scan_pnl_profile(
                "double_calendar", spot or ((sp + sc) / 2),
                {"ps": sp, "cs": sc},
                {"front": str(pos.short_exp), "back": str(pos.long_exp)},
                r, sigma, entry, n,
            )
        return _generate_payoff_chart(
            curve=profile["pnl_curve"],
            spot_price=spot,
            breakevens={"lower": profile["lower_breakeven"], "upper": profile["upper_breakeven"]},
            max_profit=profile["max_profit"],
            max_loss=profile["max_loss"],
            title=title,
        )

    # Iron Condor at-expiration
    scan_lo = lp - 10
    scan_hi = lc + 10
    curve = []
    max_profit_val = 0.0
    max_loss_val = 0.0
    lower_be = None
    upper_be = None
    prev_pnl = None

    for px_int in range(int(scan_lo * 10), int(scan_hi * 10) + 1):
        px = px_int / 10.0
        pnl_per_contract = (
            -max(0, sp - px) + max(0, lp - px)
            - max(0, px - sc) + max(0, px - lc)
            + entry
        )
        pnl = round(pnl_per_contract * 100 * n, 2)
        if px_int % 10 == 0:
            curve.append({"price": px, "pnl": pnl})
        if pnl > max_profit_val:
            max_profit_val = pnl
        if pnl < max_loss_val:
            max_loss_val = pnl
        if prev_pnl is not None:
            if prev_pnl < 0 <= pnl or prev_pnl >= 0 > pnl:
                if lower_be is None:
                    lower_be = px
                else:
                    upper_be = px
        prev_pnl = pnl

    return _generate_payoff_chart(
        curve=curve,
        spot_price=spot,
        breakevens={"lower": round(lower_be, 2) if lower_be else None,
                    "upper": round(upper_be, 2) if upper_be else None},
        max_profit=round(max_profit_val, 2),
        max_loss=round(max_loss_val, 2),
        title=title,
    )


# ---------------------------------------------------------------------------
# 10. Position payoff curve endpoint
# ---------------------------------------------------------------------------

@router.get("/positions/{position_id}/payoff")
async def position_payoff(
    request: Request, position_id: int, db: Session = Depends(get_db)
):
    """Generate at-expiration payoff curve for a saved position."""
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(404, "Position not found")

    lp, sp = pos.long_put, pos.short_put
    sc, lc = pos.short_call, pos.long_call
    entry = pos.entry_price  # per-contract net credit/debit
    n = pos.contracts
    sigma = 0.20
    r = RISK_FREE_RATE
    today_date = _today_ct()

    # Get spot price for the marker
    spot = None
    try:
        q = await _get_quote(request, pos.symbol)
        spot = q.get("last")
    except Exception:
        pass

    # For DD/DC with remaining time value, use _scan_pnl_profile
    if pos.strategy in ("double_diagonal", "double_calendar") and pos.long_exp:
        if pos.strategy == "double_diagonal":
            profile = _scan_pnl_profile(
                "double_diagonal", spot or ((sp + sc) / 2),
                {"lp": lp, "sp": sp, "sc": sc, "lc": lc},
                {"short": str(pos.short_exp), "long": str(pos.long_exp)},
                r, sigma, entry, n,
            )
        else:
            profile = _scan_pnl_profile(
                "double_calendar", spot or ((sp + sc) / 2),
                {"ps": sp, "cs": sc},
                {"front": str(pos.short_exp), "back": str(pos.long_exp)},
                r, sigma, entry, n,
            )
        return {
            "position_id": position_id,
            "spot_price": spot,
            "pnl_curve": profile["pnl_curve"],
            "max_profit": profile["max_profit"],
            "max_loss": profile["max_loss"],
            "breakevens": {
                "lower": profile["lower_breakeven"],
                "upper": profile["upper_breakeven"],
            },
        }

    # Iron Condor: at-expiration payoff (intrinsic value)
    scan_lo = lp - 10
    scan_hi = lc + 10
    curve = []
    max_profit = 0.0
    max_loss = 0.0
    lower_be = None
    upper_be = None
    prev_pnl = None

    for px_int in range(int(scan_lo * 10), int(scan_hi * 10) + 1):
        px = px_int / 10.0
        # IC at expiration: short put + short call - long put - long call
        pnl_per_contract = (
            -max(0, sp - px) + max(0, lp - px)   # put side
            - max(0, px - sc) + max(0, px - lc)   # call side
            + entry                                 # net credit received
        )
        pnl = round(pnl_per_contract * 100 * n, 2)

        if px_int % 10 == 0:
            curve.append({"price": px, "pnl": pnl})

        if pnl > max_profit:
            max_profit = pnl
        if pnl < max_loss:
            max_loss = pnl

        if prev_pnl is not None:
            if prev_pnl < 0 <= pnl or prev_pnl >= 0 > pnl:
                if lower_be is None:
                    lower_be = px
                else:
                    upper_be = px
        prev_pnl = pnl

    return {
        "position_id": position_id,
        "spot_price": spot,
        "pnl_curve": curve,
        "max_profit": round(max_profit, 2),
        "max_loss": round(max_loss, 2),
        "breakevens": {
            "lower": round(lower_be, 2) if lower_be else None,
            "upper": round(upper_be, 2) if upper_be else None,
        },
    }
