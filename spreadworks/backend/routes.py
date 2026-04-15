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

import asyncio
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
# Cache freshness TTLs (seconds).  Without these, the DB cache will happily
# serve data that's days or weeks old whenever the live upstream is briefly
# unreachable, which is the "stale data" bug users see in the builder UI.
# ---------------------------------------------------------------------------
GEX_CACHE_MAX_AGE_OPEN_SEC = 15 * 60            # 15 min while market is open
GEX_CACHE_MAX_AGE_CLOSED_SEC = 20 * 60 * 60     # 20h when closed (prior session OK)
CANDLE_CACHE_MAX_AGE_OPEN_SEC = 10 * 60         # 10 min while market is open
CANDLE_CACHE_MAX_AGE_CLOSED_SEC = 20 * 60 * 60  # 20h when closed
# If GEX's reported spot_price disagrees with the current market by more than
# this fraction, we flag the snapshot as stale even if the cache is "fresh".
GEX_SPOT_DRIFT_THRESHOLD = 0.02                 # 2%

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


def _cache_age_seconds(fetched_at: datetime | None) -> float | None:
    """Return age in seconds of a cache row's fetched_at, or None if unknown."""
    if fetched_at is None:
        return None
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - fetched_at).total_seconds()


def _read_cached_candles(
    symbol: str, interval: str = "15min", max_age_sec: float | None = None
) -> dict | None:
    if SessionLocal is None:
        return None
    try:
        db = SessionLocal()
        try:
            row = db.query(CandleCache).filter(
                CandleCache.symbol == symbol,
                CandleCache.interval == interval,
            ).first()
            if not row or not row.candles_json:
                return None
            age = _cache_age_seconds(row.fetched_at)
            if max_age_sec is not None and age is not None and age > max_age_sec:
                logger.info(
                    "[candles] Skipping stale cache for %s %s — age %.0fs > max %.0fs",
                    symbol, interval, age, max_age_sec,
                )
                return None
            return {
                "candles": json.loads(row.candles_json),
                "last_price": row.last_price,
                "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
                "age_seconds": age,
            }
        finally:
            db.close()
    except Exception:
        pass
    return None


def _read_cached_gex(symbol: str, max_age_sec: float | None = None) -> dict | None:
    if SessionLocal is None:
        return None
    try:
        db = SessionLocal()
        try:
            row = db.query(GexCache).filter(GexCache.symbol == symbol).first()
            if not row:
                return None
            age = _cache_age_seconds(row.fetched_at)
            if max_age_sec is not None and age is not None and age > max_age_sec:
                logger.info(
                    "[gex] Skipping stale cache for %s — age %.0fs > max %.0fs",
                    symbol, age, max_age_sec,
                )
                return None
            return {
                "flip_point": row.flip_point,
                "call_wall": row.call_wall,
                "put_wall": row.put_wall,
                "gamma_regime": row.gamma_regime,
                "spot_price": row.spot_price,
                "vix": row.vix,
                "source": f"{row.source}_cached",
                "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
                "age_seconds": age,
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
    except Exception as e:
        logger.warning(f"[candles] Tradier timesales failed for {symbol}: {e}")

    # Fallback: if timesales returned nothing, try quote then cache
    if not candles:
        try:
            q = await _get_quote(request, symbol)
            last_price = q.get("last")
            if last_price:
                _cache_quote(symbol, last_price)
        except Exception as e:
            logger.warning(f"[candles] Quote fallback failed for {symbol}: {e}")

    # If still no candles (market closed, API down, etc.), read from cache with
    # a TTL so we never serve days-old data as if it were current.
    if not candles:
        max_age = (
            CANDLE_CACHE_MAX_AGE_OPEN_SEC
            if _is_market_open_now()
            else CANDLE_CACHE_MAX_AGE_CLOSED_SEC
        )
        cached = _read_cached_candles(symbol, interval, max_age_sec=max_age)
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


async def _annotate_gex_staleness(
    request: Request, result: dict, symbol: str
) -> dict:
    """Compare GEX spot_price against current market quote. Flag as stale if
    the upstream snapshot disagrees with reality (e.g. walls reported for
    yesterday's price range while SPY has moved several percent since)."""
    try:
        current_spot = None
        try:
            q = await _get_quote(request, symbol)
            current_spot = q.get("last")
        except Exception:
            cached_q = _read_cached_quote(symbol)
            if cached_q:
                current_spot = cached_q.get("last")

        gex_spot = result.get("spot_price")
        if current_spot and gex_spot and gex_spot > 0:
            drift = abs(current_spot - gex_spot) / gex_spot
            result["current_spot"] = current_spot
            result["spot_drift_pct"] = round(drift * 100, 3)
            if drift > GEX_SPOT_DRIFT_THRESHOLD:
                result["stale"] = True
                result["stale_reason"] = (
                    f"GEX spot ${gex_spot:.2f} differs from market ${current_spot:.2f} "
                    f"by {drift * 100:.1f}% (> {GEX_SPOT_DRIFT_THRESHOLD * 100:.0f}%)"
                )
    except Exception as e:
        logger.debug("[gex] Staleness annotation failed: %s", e)
    return result


@router.get("/gex")
async def get_gex(request: Request, symbol: str = "SPY"):
    """Proxy GEX levels from AlphaGEX. Falls back to cache when unavailable.

    Every response carries ``fetched_at`` and, when the upstream snapshot looks
    stale (too old, or reported spot diverges from the market), a ``stale:true``
    flag with ``stale_reason`` so the frontend can warn the user rather than
    silently render days-old walls."""
    import httpx

    http = request.app.state.http
    _timeout = 5.0
    now_iso = datetime.now(timezone.utc).isoformat()

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
            upstream_fetched_at = d.get("fetched_at") or d.get("data_timestamp")
            result = {
                "flip_point": fp_obj.get("current") if isinstance(fp_obj, dict) else fp_obj,
                "call_wall": gw.get("call_wall") if isinstance(gw, dict) else None,
                "put_wall": gw.get("put_wall") if isinstance(gw, dict) else None,
                "gamma_regime": d.get("gamma_regime") or ms.get("gamma_regime"),
                "spot_price": d.get("spot_price"),
                "vix": d.get("vix"),
                "source": "watchtower",
                "fetched_at": upstream_fetched_at or now_iso,
                "stale": False,
            }
            _cache_gex(symbol, result)
            return await _annotate_gex_staleness(request, result, symbol)
    except httpx.TimeoutException:
        logger.warning(f"[gex] Watchtower timeout for {symbol}")
    except Exception as e:
        logger.warning(f"[gex] Watchtower fetch failed for {symbol}: {e}")

    # Fallback to simple GEX endpoint
    try:
        resp = await http.get(
            f"{ALPHAGEX_BASE_URL}/api/gex/{symbol}",
            timeout=_timeout,
        )
        if resp.status_code == 200:
            body = resp.json()
            d = body.get("data", body)
            upstream_fetched_at = d.get("fetched_at") or d.get("data_timestamp")
            result = {
                "flip_point": d.get("flip_point"),
                "call_wall": d.get("call_wall"),
                "put_wall": d.get("put_wall"),
                "gamma_regime": d.get("regime") or d.get("gamma_regime"),
                "spot_price": d.get("spot_price"),
                "vix": d.get("vix"),
                "source": "gex",
                "fetched_at": upstream_fetched_at or now_iso,
                "stale": False,
            }
            _cache_gex(symbol, result)
            return await _annotate_gex_staleness(request, result, symbol)
    except httpx.TimeoutException:
        logger.warning(f"[gex] Simple GEX timeout for {symbol}")
    except Exception as e:
        logger.warning(f"[gex] Simple GEX fetch failed for {symbol}: {e}")

    # All live sources failed — try cache, but only if it's not expired.
    max_age = (
        GEX_CACHE_MAX_AGE_OPEN_SEC
        if _is_market_open_now()
        else GEX_CACHE_MAX_AGE_CLOSED_SEC
    )
    cached = _read_cached_gex(symbol, max_age_sec=max_age)
    if cached:
        # Cache came back — flag it explicitly so the UI can label it as cached
        # data rather than live, and still run the spot-drift sanity check.
        cached["stale"] = False
        return await _annotate_gex_staleness(request, cached, symbol)

    # Check if there's an expired cache row we deliberately skipped — surface
    # that to the caller instead of silently returning "unavailable", so the
    # frontend can show "data is X minutes old" rather than a mystery error.
    expired = _read_cached_gex(symbol, max_age_sec=None)
    if expired:
        expired["stale"] = True
        expired["stale_reason"] = (
            f"Upstream GEX unavailable; last cached snapshot is "
            f"{int((expired.get('age_seconds') or 0) / 60)} min old"
        )
        return expired

    return {
        "error": "GEX data unavailable",
        "detail": "Could not reach AlphaGEX backend",
        "fetched_at": now_iso,
        "stale": True,
    }


# ---------------------------------------------------------------------------
# 3. Expirations
# ---------------------------------------------------------------------------


@router.get("/expirations")
async def get_expirations(request: Request, symbol: str = "SPY"):
    """Return available option expirations from Tradier with DTE labels."""
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

    # Annotate each expiration with DTE
    today = _today_ct()
    annotated = []
    for d in date_list:
        try:
            exp_date = datetime.strptime(d, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            annotated.append({"date": d, "dte": dte})
        except (ValueError, TypeError):
            annotated.append({"date": d, "dte": None})

    return {"symbol": symbol, "expirations": date_list, "expirations_with_dte": annotated}


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
    if gex.get("stale"):
        # Don't silently suggest strikes built from stale walls — that's the
        # exact "call wall $652 while SPY is $695" bug.  Tell the caller so
        # the UI can refuse to populate and prompt the user.
        raise HTTPException(
            409,
            gex.get("stale_reason") or "GEX snapshot is stale — refusing to suggest strikes",
        )
    flip = gex.get("flip_point")
    call_wall = gex.get("call_wall")
    put_wall = gex.get("put_wall")
    spot = gex.get("spot_price")
    regime = gex.get("gamma_regime")

    # Prefer the live market spot (passed through from the staleness annotation)
    # over the possibly-older spot that came back with the GEX snapshot, so
    # suggestions are anchored to current price.
    if gex.get("current_spot"):
        spot = gex["current_spot"]

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

    # Credit strategies (IC, Iron Butterfly) always suggest 0DTE as the
    # nearest trading day so users can explore them anytime (weekends use
    # next Monday).  Non-credit strategies keep the next-Friday pattern.
    credit_strategies = {"iron_condor", "iron_butterfly"}
    is_credit = strategy in credit_strategies
    if is_credit:
        # Find nearest weekday (today if Mon-Fri, else next Monday)
        dte_date = today
        while dte_date.weekday() >= 5:  # Sat=5, Sun=6
            dte_date += timedelta(days=1)
        credit_exp = dte_date.isoformat()
    else:
        credit_exp = front_exp

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
            "expiration": credit_exp,
        }
        is_0dte = credit_exp == today.isoformat()
        dte_note = "0DTE" if is_0dte else f"exp {credit_exp}"
        rationale = (
            f"Iron Condor: short strikes at GEX walls "
            f"(put wall ${short_put}, call wall ${short_call}). "
            f"Long wings ${wing_offset} wide. "
            f"{dte_note}. "
            f"Regime: {regime or 'UNKNOWN'}."
        )
    elif strategy == "butterfly":
        # Butterfly centered at flip point (neutral bet on pin)
        center = _round_strike(flip)
        lower_strike = _round_strike(center - wing_offset)
        upper_strike = _round_strike(center + wing_offset)

        legs = {
            "lower_strike": lower_strike,
            "middle_strike": center,
            "upper_strike": upper_strike,
            "option_type": "call",
            "expiration": front_exp,
        }
        rationale = (
            f"Butterfly centered at GEX flip point ${center}. "
            f"Wings ${wing_offset} wide (${lower_strike}/${center}/${upper_strike}). "
            f"Exp {front_exp}. Regime: {regime or 'UNKNOWN'}."
        )
    elif strategy == "iron_butterfly":
        # Iron Butterfly: short straddle at flip, wings at walls
        short_strike = _round_strike(flip)
        lp_strike = _round_strike(short_strike - wing_offset)
        lc_strike = _round_strike(short_strike + wing_offset)

        legs = {
            "long_put_strike": lp_strike,
            "short_strike": short_strike,
            "long_call_strike": lc_strike,
            "expiration": credit_exp,
        }
        is_0dte = credit_exp == today.isoformat()
        dte_note = "0DTE" if is_0dte else f"exp {credit_exp}"
        rationale = (
            f"Iron Butterfly: short straddle at flip ${short_strike}, "
            f"wings at ${lp_strike}/${lc_strike}. "
            f"{dte_note}. "
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
    elif strategy == "butterfly":
        lower, middle, upper = strikes["lower"], strikes["middle"], strikes["upper"]
        is_call = strikes.get("is_call", True)
        T_exp = _tte(expirations["exp"])
        scan_lo = lower - 20
        scan_hi = upper + 20
    elif strategy == "iron_butterfly":
        lp = strikes["lp"]
        short = strikes["short"]
        lc = strikes["lc"]
        T_exp = _tte(expirations["exp"])
        scan_lo = lp - 20
        scan_hi = lc + 20
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
                - entry_cost
            ) * 100 * n
        elif strategy == "butterfly":
            # Butterfly: buy 1 lower, sell 2 middle, buy 1 upper (same type)
            if is_call:
                pnl = (
                    max(0, px - lower)       # long lower call
                    - 2 * max(0, px - middle) # short 2x middle call
                    + max(0, px - upper)      # long upper call
                    - entry_cost
                ) * 100 * n
            else:
                pnl = (
                    max(0, lower - px)       # long lower put (OTM)
                    - 2 * max(0, middle - px) # short 2x middle put
                    + max(0, upper - px)      # long upper put (ITM)
                    - entry_cost
                ) * 100 * n
        elif strategy == "iron_butterfly":
            # Iron Butterfly: long put wing, short ATM put+call, long call wing
            pnl = (
                max(0, lp - px)       # long put payoff
                - max(0, short - px)  # short ATM put
                - max(0, px - short)  # short ATM call
                + max(0, px - lc)     # long call payoff
                - entry_cost
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


def _build_pnl_grid(
    strategy: str,
    S: float,
    strikes: dict[str, float],
    expirations: dict[str, str],
    r: float,
    sigma: float,
    entry_cost: float,
    n: int,
) -> dict:
    """Build a 2D P&L grid: rows = price levels, columns = time slices.

    Returns { time_slices: [...], price_levels: [...], rows: [[cell, ...], ...] }
    Each cell: { pnl, pnl_pct, contract_value }
    """
    today_date = _today_ct()

    def _parse_exp(d: str):
        return datetime.strptime(d, "%Y-%m-%d").date()

    # Determine the front (nearest) expiration for time slices
    if strategy == "double_diagonal":
        front_exp = _parse_exp(expirations["short"])
        back_exp = _parse_exp(expirations["long"])
    elif strategy in ("iron_condor", "butterfly", "iron_butterfly"):
        front_exp = _parse_exp(expirations["exp"])
        back_exp = front_exp
    else:  # double_calendar
        front_exp = _parse_exp(expirations["front"])
        back_exp = _parse_exp(expirations["back"])

    # Build time slices: daily from today to front_exp, plus intraday on exp day
    time_slices = []  # list of { label, dte_frac }
    days_to_front = max((front_exp - today_date).days, 0)

    if days_to_front == 0:
        # Already expiration day — intraday slices
        for hour in [9, 11, 13, 15, 16]:
            frac = max((16 - hour), 0) / (365.0 * 6.5)  # rough fraction of trading day
            label = f"{front_exp.strftime('%b %d')} {hour}:00"
            time_slices.append({"label": label, "dte_frac": frac, "is_expiry": hour == 16})
    else:
        for d in range(days_to_front + 1):
            dt = today_date + timedelta(days=d)
            dte = max((front_exp - dt).days, 0) / 365.0
            is_exp = dt == front_exp
            label = dt.strftime("%b %d")
            if is_exp:
                label += " EXP"
            if d == 0:
                label = "Now"
            time_slices.append({"label": label, "dte_frac": dte, "is_expiry": is_exp})

    # Build price levels: 20 prices centered on spot
    all_strikes = [v for v in strikes.values() if isinstance(v, (int, float))]
    strike_spread = max(all_strikes) - min(all_strikes) if all_strikes else 10
    step = 2.0 if strike_spread > 20 else 1.0
    n_levels = 10  # 10 above + 10 below + spot = 21 rows
    center = round(S / step) * step
    price_levels = [center + (i - n_levels) * step for i in range(2 * n_levels + 1)]

    # Max risk for percentage calculations
    max_risk = abs(entry_cost * 100 * n) if entry_cost != 0 else 1.0

    # Build grid
    rows = []
    for px in price_levels:
        row = []
        for ts in time_slices:
            T = ts["dte_frac"]
            # Back-expiration time remaining at this slice
            if strategy == "double_diagonal":
                T_back = max((back_exp - today_date).days / 365.0 - (days_to_front / 365.0 - T), T + 1 / 365.0)
                pnl = (
                    _bs_price(px, strikes["lp"], T_back, r, sigma, False)
                    - (max(0, strikes["sp"] - px) if T <= 0 else _bs_price(px, strikes["sp"], T, r, sigma, False))
                    - (max(0, px - strikes["sc"]) if T <= 0 else _bs_price(px, strikes["sc"], T, r, sigma, True))
                    + _bs_price(px, strikes["lc"], T_back, r, sigma, True)
                    - entry_cost
                ) * 100 * n
            elif strategy == "iron_condor":
                if T <= 0:
                    pnl = (
                        max(0, strikes["lp"] - px)
                        - max(0, strikes["sp"] - px)
                        - max(0, px - strikes["sc"])
                        + max(0, px - strikes["lc"])
                        - entry_cost
                    ) * 100 * n
                else:
                    pnl = (
                        _bs_price(px, strikes["lp"], T, r, sigma, False)
                        - _bs_price(px, strikes["sp"], T, r, sigma, False)
                        - _bs_price(px, strikes["sc"], T, r, sigma, True)
                        + _bs_price(px, strikes["lc"], T, r, sigma, True)
                        - entry_cost
                    ) * 100 * n
            elif strategy == "butterfly":
                is_call_bf = strikes.get("is_call", True)
                if T <= 0:
                    if is_call_bf:
                        pnl = (max(0, px - strikes["lower"]) - 2 * max(0, px - strikes["middle"]) + max(0, px - strikes["upper"]) - entry_cost) * 100 * n
                    else:
                        pnl = (max(0, strikes["lower"] - px) - 2 * max(0, strikes["middle"] - px) + max(0, strikes["upper"] - px) - entry_cost) * 100 * n
                else:
                    pnl = (
                        _bs_price(px, strikes["lower"], T, r, sigma, is_call_bf)
                        - 2 * _bs_price(px, strikes["middle"], T, r, sigma, is_call_bf)
                        + _bs_price(px, strikes["upper"], T, r, sigma, is_call_bf)
                        - entry_cost
                    ) * 100 * n
            elif strategy == "iron_butterfly":
                if T <= 0:
                    pnl = (
                        max(0, strikes["lp"] - px)
                        - max(0, strikes["short"] - px)
                        - max(0, px - strikes["short"])
                        + max(0, px - strikes["lc"])
                        - entry_cost
                    ) * 100 * n
                else:
                    pnl = (
                        _bs_price(px, strikes["lp"], T, r, sigma, False)
                        - _bs_price(px, strikes["short"], T, r, sigma, False)
                        - _bs_price(px, strikes["short"], T, r, sigma, True)
                        + _bs_price(px, strikes["lc"], T, r, sigma, True)
                        - entry_cost
                    ) * 100 * n
            else:  # double_calendar
                T_back_remaining = max((back_exp - today_date).days / 365.0 - (days_to_front / 365.0 - T), T + 1 / 365.0)
                if T <= 0:
                    pnl = (
                        - max(0, strikes["ps"] - px)
                        + _bs_price(px, strikes["ps"], T_back_remaining, r, sigma, False)
                        - max(0, px - strikes["cs"])
                        + _bs_price(px, strikes["cs"], T_back_remaining, r, sigma, True)
                        - entry_cost
                    ) * 100 * n
                else:
                    pnl = (
                        - _bs_price(px, strikes["ps"], T, r, sigma, False)
                        + _bs_price(px, strikes["ps"], T_back_remaining, r, sigma, False)
                        - _bs_price(px, strikes["cs"], T, r, sigma, True)
                        + _bs_price(px, strikes["cs"], T_back_remaining, r, sigma, True)
                        - entry_cost
                    ) * 100 * n

            contract_value = round(pnl + entry_cost * 100 * n, 2)
            row.append({
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl / max_risk * 100, 1) if max_risk else 0,
                "contract_value": contract_value,
            })
        rows.append(row)

    return {
        "time_slices": [{"label": ts["label"], "is_expiry": ts["is_expiry"]} for ts in time_slices],
        "price_levels": [round(px, 2) for px in price_levels],
        "rows": rows,
        "spot_price": S,
        "max_profit": max(cell["pnl"] for row in rows for cell in row) if rows else 0,
        "max_loss": min(cell["pnl"] for row in rows for cell in row) if rows else 0,
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
            {"leg": "Long Put", "type": "long", "strike": lp, "exp": long_exp, "price": round(p_lp, 4), "iv": round(iv_lp, 4), "theoretical": theo_lp, "greeks": {k: round(v, 6) for k, v in g_lp.items()}},
            {"leg": "Short Put", "type": "short", "strike": sp, "exp": short_exp, "price": round(p_sp, 4), "iv": round(iv_sp, 4), "theoretical": theo_sp, "greeks": {k: round(v, 6) for k, v in g_sp.items()}},
            {"leg": "Short Call", "type": "short", "strike": sc, "exp": short_exp, "price": round(p_sc, 4), "iv": round(iv_sc, 4), "theoretical": theo_sc, "greeks": {k: round(v, 6) for k, v in g_sc.items()}},
            {"leg": "Long Call", "type": "long", "strike": lc, "exp": long_exp, "price": round(p_lc, 4), "iv": round(iv_lc, 4), "theoretical": theo_lc, "greeks": {k: round(v, 6) for k, v in g_lc.items()}},
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
            {"leg": "Long Put", "type": "long", "strike": lp, "exp": exp, "price": round(p_lp, 4), "iv": round(iv_lp, 4), "theoretical": theo_lp, "greeks": {k: round(v, 6) for k, v in g_lp.items()}},
            {"leg": "Short Put", "type": "short", "strike": sp, "exp": exp, "price": round(p_sp, 4), "iv": round(iv_sp, 4), "theoretical": theo_sp, "greeks": {k: round(v, 6) for k, v in g_sp.items()}},
            {"leg": "Short Call", "type": "short", "strike": sc, "exp": exp, "price": round(p_sc, 4), "iv": round(iv_sc, 4), "theoretical": theo_sc, "greeks": {k: round(v, 6) for k, v in g_sc.items()}},
            {"leg": "Long Call", "type": "long", "strike": lc, "exp": exp, "price": round(p_lc, 4), "iv": round(iv_lc, 4), "theoretical": theo_lc, "greeks": {k: round(v, 6) for k, v in g_lc.items()}},
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
            {"leg": "Short Front Put", "type": "short", "strike": ps, "exp": front_exp, "price": round(p_fp, 4), "iv": round(iv_fp, 4), "theoretical": theo_fp, "greeks": {k: round(v, 6) for k, v in g_fp.items()}},
            {"leg": "Long Back Put", "type": "long", "strike": ps, "exp": back_exp, "price": round(p_bp, 4), "iv": round(iv_bp, 4), "theoretical": theo_bp, "greeks": {k: round(v, 6) for k, v in g_bp.items()}},
            {"leg": "Short Front Call", "type": "short", "strike": cs, "exp": front_exp, "price": round(p_fc, 4), "iv": round(iv_fc, 4), "theoretical": theo_fc, "greeks": {k: round(v, 6) for k, v in g_fc.items()}},
            {"leg": "Long Back Call", "type": "long", "strike": cs, "exp": back_exp, "price": round(p_bc, 4), "iv": round(iv_bc, 4), "theoretical": theo_bc, "greeks": {k: round(v, 6) for k, v in g_bc.items()}},
        ]
    elif body.strategy == "butterfly":
        lower = float(legs.get("lowerStrike") or legs.get("lower_strike", 0))
        middle = float(legs.get("middleStrike") or legs.get("middle_strike", 0))
        upper = float(legs.get("upperStrike") or legs.get("upper_strike", 0))
        opt_type = str(legs.get("optionType") or legs.get("option_type", "call"))
        exp = str(legs.get("expiration") or "")
        is_call = opt_type.lower() == "call"

        if not all([lower, middle, upper, exp]):
            raise HTTPException(422, "All 3 strikes and expiration required for Butterfly")

        T_exp = _tte(exp)

        p_lower, iv_lower, theo_lower = _price_or_bs(lower, T_exp, is_call, exp)
        p_middle, iv_middle, theo_middle = _price_or_bs(middle, T_exp, is_call, exp)
        p_upper, iv_upper, theo_upper = _price_or_bs(upper, T_exp, is_call, exp)

        # Buy 1 lower + Buy 1 upper - Sell 2 middle
        entry_cost = p_lower + p_upper - 2 * p_middle
        net_debit = entry_cost * 100 * n

        g_lower = _bs_greeks(S, lower, T_exp, r, iv_lower, is_call)
        g_middle = _bs_greeks(S, middle, T_exp, r, iv_middle, is_call)
        g_upper = _bs_greeks(S, upper, T_exp, r, iv_upper, is_call)

        greeks = {
            k: round((g_lower[k] - 2 * g_middle[k] + g_upper[k]) * n, 6)
            for k in ("delta", "gamma", "theta", "vega")
        }

        avg_sigma = sum([iv_lower, iv_middle, iv_middle, iv_upper]) / 4
        profile = _scan_pnl_profile(
            "butterfly", S,
            {"lower": lower, "middle": middle, "upper": upper, "is_call": is_call},
            {"exp": exp},
            r, avg_sigma, entry_cost, n,
        )

        type_label = "Call" if is_call else "Put"
        leg_detail = [
            {"leg": f"Long {type_label} (Lower)", "type": "long", "strike": lower, "exp": exp, "price": round(p_lower, 4), "iv": round(iv_lower, 4), "theoretical": theo_lower, "greeks": {k: round(v, 6) for k, v in g_lower.items()}},
            {"leg": f"Short {type_label} x2 (Middle)", "type": "short", "strike": middle, "exp": exp, "price": round(p_middle * 2, 4), "iv": round(iv_middle, 4), "theoretical": theo_middle, "greeks": {k: round(v * 2, 6) for k, v in g_middle.items()}},
            {"leg": f"Long {type_label} (Upper)", "type": "long", "strike": upper, "exp": exp, "price": round(p_upper, 4), "iv": round(iv_upper, 4), "theoretical": theo_upper, "greeks": {k: round(v, 6) for k, v in g_upper.items()}},
        ]

    elif body.strategy == "iron_butterfly":
        lp = float(legs.get("longPutStrike") or legs.get("long_put_strike", 0))
        short = float(legs.get("shortStrike") or legs.get("short_strike", 0))
        lc = float(legs.get("longCallStrike") or legs.get("long_call_strike", 0))
        exp = str(legs.get("expiration") or "")

        if not all([lp, short, lc, exp]):
            raise HTTPException(422, "Long put, short strike, long call, and expiration required for Iron Butterfly")

        T_exp = _tte(exp)

        p_lp, iv_lp, theo_lp = _price_or_bs(lp, T_exp, False, exp)
        p_sp, iv_sp, theo_sp = _price_or_bs(short, T_exp, False, exp)
        p_sc, iv_sc, theo_sc = _price_or_bs(short, T_exp, True, exp)
        p_lc, iv_lc, theo_lc = _price_or_bs(lc, T_exp, True, exp)

        # Credit strategy: sell ATM straddle, buy wings
        entry_cost = p_lp + p_lc - p_sp - p_sc  # negative = net credit
        net_debit = entry_cost * 100 * n

        g_lp = _bs_greeks(S, lp, T_exp, r, iv_lp, False)
        g_sp = _bs_greeks(S, short, T_exp, r, iv_sp, False)
        g_sc = _bs_greeks(S, short, T_exp, r, iv_sc, True)
        g_lc = _bs_greeks(S, lc, T_exp, r, iv_lc, True)

        greeks = {
            k: round((g_lp[k] - g_sp[k] - g_sc[k] + g_lc[k]) * n, 6)
            for k in ("delta", "gamma", "theta", "vega")
        }

        avg_sigma = sum([iv_lp, iv_sp, iv_sc, iv_lc]) / 4
        profile = _scan_pnl_profile(
            "iron_butterfly", S,
            {"lp": lp, "short": short, "lc": lc},
            {"exp": exp},
            r, avg_sigma, entry_cost, n,
        )

        leg_detail = [
            {"leg": "Long Put (Wing)", "type": "long", "strike": lp, "exp": exp, "price": round(p_lp, 4), "iv": round(iv_lp, 4), "theoretical": theo_lp, "greeks": {k: round(v, 6) for k, v in g_lp.items()}},
            {"leg": "Short Put (ATM)", "type": "short", "strike": short, "exp": exp, "price": round(p_sp, 4), "iv": round(iv_sp, 4), "theoretical": theo_sp, "greeks": {k: round(v, 6) for k, v in g_sp.items()}},
            {"leg": "Short Call (ATM)", "type": "short", "strike": short, "exp": exp, "price": round(p_sc, 4), "iv": round(iv_sc, 4), "theoretical": theo_sc, "greeks": {k: round(v, 6) for k, v in g_sc.items()}},
            {"leg": "Long Call (Wing)", "type": "long", "strike": lc, "exp": exp, "price": round(p_lc, 4), "iv": round(iv_lc, 4), "theoretical": theo_lc, "greeks": {k: round(v, 6) for k, v in g_lc.items()}},
        ]

    else:
        raise HTTPException(400, f"Unknown strategy: {body.strategy}")

    # Compute average IV across legs
    avg_iv = None
    if leg_detail:
        ivs = [leg["iv"] for leg in leg_detail if leg.get("iv") and leg["iv"] > 0]
        avg_iv = round(sum(ivs) / len(ivs), 4) if ivs else None

    # Build P&L heatmap grid
    if body.strategy == "double_diagonal":
        grid_strikes = {"lp": lp, "sp": sp, "sc": sc, "lc": lc}
        grid_exps = {"short": short_exp, "long": long_exp}
    elif body.strategy == "iron_condor":
        grid_strikes = {"lp": lp, "sp": sp, "sc": sc, "lc": lc}
        grid_exps = {"exp": exp}
    elif body.strategy == "butterfly":
        grid_strikes = {"lower": lower, "middle": middle, "upper": upper, "is_call": is_call}
        grid_exps = {"exp": exp}
    elif body.strategy == "iron_butterfly":
        grid_strikes = {"lp": lp, "short": short, "lc": lc}
        grid_exps = {"exp": exp}
    else:
        grid_strikes = {"ps": ps, "cs": cs}
        grid_exps = {"front": front_exp, "back": back_exp}

    pnl_grid = _build_pnl_grid(
        body.strategy, S, grid_strikes, grid_exps,
        r, avg_sigma, entry_cost, n,
    )

    # net_debit < 0 means net credit (IC, credit spreads)
    rounded_debit = round(net_debit, 2)
    return {
        "symbol": body.symbol,
        "strategy": body.strategy,
        "contracts": n,
        "net_debit": rounded_debit,
        "net_credit": round(-rounded_debit, 2) if rounded_debit < 0 else None,
        "max_profit": profile["max_profit"],
        "max_loss": profile["max_loss"],
        "lower_breakeven": profile["lower_breakeven"],
        "upper_breakeven": profile["upper_breakeven"],
        "probability_of_profit": profile["probability_of_profit"],
        "greeks": greeks,
        "pnl_curve": profile["pnl_curve"],
        "pnl_grid": pnl_grid,
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
    "butterfly": "Butterfly",
    "iron_butterfly": "Iron Butterfly",
}

# Strategies where entry_price represents a credit received (entry_cost < 0).
# For debit strategies, entry_price = |debit per share| (positive), but
# the P&L formula must negate it.
CREDIT_STRATEGIES = {"iron_condor", "iron_butterfly"}


def _compute_unrealized_pnl(
    entry_price: float,
    val: float,
    contracts: int,
    strategy: str,
    max_profit: float | None = None,
    max_loss: float | None = None,
) -> float:
    """Compute unrealized P&L with correct sign handling for credit vs debit strategies.

    For CREDIT strategies (IC, Iron Butterfly):
        P&L = (entry_price - val) * 100 * contracts
        entry_price = credit per share (positive), val = cost to close (positive, shrinks to 0)

    For DEBIT strategies (DD, DC, Butterfly):
        P&L = -(entry_price + val) * 100 * contracts
        entry_price = |debit per share| (positive), val = short - long (negative when profitable)
    """
    if strategy in CREDIT_STRATEGIES:
        raw = (entry_price - val) * 100 * contracts
    else:
        # Debit: you paid |entry_price|. Current value of position = -val.
        # P&L = current_value - cost = (-val) - entry_price = -(val + entry_price)
        raw = -(val + entry_price) * 100 * contracts

    pnl = round(raw, 2)

    # Cap at theoretical boundaries and log violations for monitoring
    if max_profit is not None and pnl > abs(max_profit):
        logger.warning(
            "P&L sanity violation: raw=%.2f exceeds max_profit=%.2f for %s (entry_price=%.4f, val=%.4f)",
            pnl, max_profit, strategy, entry_price, val,
        )
        pnl = round(abs(max_profit), 2)
    if max_loss is not None and pnl < -abs(max_loss):
        logger.warning(
            "P&L sanity violation: raw=%.2f exceeds max_loss=%.2f for %s (entry_price=%.4f, val=%.4f)",
            pnl, max_loss, strategy, entry_price, val,
        )
        pnl = -round(abs(max_loss), 2)

    return pnl


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
    close_price: float = 0.0  # per-contract debit to close (0 = expired worthless)


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

    # Guardrail: warn if max_profit/max_loss boundaries are missing
    if pos.max_profit is None or pos.max_loss is None:
        logger.warning(
            "Position %d saved without P&L boundaries: max_profit=%s, max_loss=%s. "
            "P&L cap guardrails will not function.",
            pos.id, pos.max_profit, pos.max_loss,
        )

    return _pos_to_dict(pos)


# --- GET /positions/summary (portfolio roll-up) ---
# NOTE: must be defined BEFORE /positions/{position_id} to avoid path conflict
@router.get("/positions/summary")
async def positions_summary(request: Request, db: Session = Depends(get_db)):
    open_positions = db.query(Position).filter(Position.status == "open").all()
    closed_positions = db.query(Position).filter(Position.status == "closed").all()

    net_premium = sum(
        p.entry_credit if p.strategy in CREDIT_STRATEGIES else -p.entry_credit
        for p in open_positions
    )
    total_collateral = sum(abs(p.max_loss or 0) for p in open_positions)
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
        "total_credit": round(net_premium, 2),
        "net_premium": round(net_premium, 2),
        "total_collateral": round(total_collateral, 2),
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

    realized = _compute_unrealized_pnl(
        pos.entry_price, body.close_price, pos.contracts, pos.strategy,
        pos.max_profit, pos.max_loss,
    )

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


# --- Live option quote helper ---

async def _get_leg_quotes(
    request: Request,
    symbol: str,
    legs: list[dict],
) -> dict[str, dict]:
    """Fetch live mid prices AND IV for option legs from Tradier chains.

    *legs* is a list of dicts, each with keys:
        strike (float), exp (str YYYY-MM-DD), option_type ("put" | "call"), key (str)

    Returns {key: {"mid": float|None, "iv": float|None}}.
    """
    by_exp: dict[str, list[dict]] = {}
    for leg in legs:
        exp = str(leg["exp"])
        by_exp.setdefault(exp, []).append(leg)

    result: dict[str, dict] = {leg["key"]: {"mid": None, "iv": None} for leg in legs}

    for exp, exp_legs in by_exp.items():
        try:
            chain = await _fetch_chain_raw(request, symbol, exp)
        except Exception:
            continue

        # Build lookup: (strike, option_type) -> {mid, iv}
        lookup: dict[tuple[float, str], dict] = {}
        for o in chain:
            strike = o.get("strike")
            otype = (o.get("option_type") or "").lower()
            bid = o.get("bid")
            ask = o.get("ask")
            greeks = o.get("greeks") or {}
            if strike is not None and bid is not None and ask is not None:
                iv = greeks.get("mid_iv") or greeks.get("smv_vol")
                lookup[(float(strike), otype)] = {
                    "mid": round((bid + ask) / 2, 4),
                    "iv": float(iv) if iv is not None else None,
                }

        for leg in exp_legs:
            found = lookup.get((float(leg["strike"]), leg["option_type"]))
            if found:
                result[leg["key"]] = found

    return result


def _spread_val_from_quotes(quotes: dict[str, dict]) -> float | None:
    """Compute net spread value from leg mid prices.

    Value = (short legs we'd buy back) - (long legs we'd sell to close).
    """
    sp = quotes.get("short_put", {}).get("mid")
    sc = quotes.get("short_call", {}).get("mid")
    lp = quotes.get("long_put", {}).get("mid")
    lc = quotes.get("long_call", {}).get("mid")
    if any(v is None for v in [sp, sc, lp, lc]):
        return None
    return sp + sc - lp - lc


def _bs_spread_val(pos, current_price: float, leg_ivs: dict[str, float | None] | None = None) -> float:
    """Black-Scholes fallback spread valuation.

    Uses per-leg IV from Tradier when available, otherwise falls back to 20%.
    """
    r = RISK_FREE_RATE
    default_sigma = 0.20
    today_date = _today_ct()

    def tte(d):
        return max((d - today_date).days, 0) / 365.0 if d else 0

    def iv_for(key: str) -> float:
        if leg_ivs and leg_ivs.get(key) is not None:
            return leg_ivs[key]
        return default_sigma

    if pos.strategy == "double_diagonal" and pos.long_exp:
        T_short = tte(pos.short_exp)
        T_long = tte(pos.long_exp)
        return (
            _bs_price(current_price, pos.short_put, T_short, r, iv_for("short_put"), False)
            + _bs_price(current_price, pos.short_call, T_short, r, iv_for("short_call"), True)
            - _bs_price(current_price, pos.long_put, T_long, r, iv_for("long_put"), False)
            - _bs_price(current_price, pos.long_call, T_long, r, iv_for("long_call"), True)
        )
    elif pos.strategy == "double_calendar" and pos.long_exp:
        T_front = tte(pos.short_exp)
        T_back = tte(pos.long_exp)
        return (
            _bs_price(current_price, pos.short_put, T_front, r, iv_for("short_put"), False)
            + _bs_price(current_price, pos.short_call, T_front, r, iv_for("short_call"), True)
            - _bs_price(current_price, pos.long_put, T_back, r, iv_for("long_put"), False)
            - _bs_price(current_price, pos.long_call, T_back, r, iv_for("long_call"), True)
        )
    elif pos.strategy == "butterfly":
        # Butterfly: all legs are same type (calls by default since we don't store option_type).
        # Stored as: long_put=lower, short_put=middle, short_call=middle, long_call=upper.
        # val = 2*BS(middle) - BS(lower) - BS(upper)  (short minus long)
        T = tte(pos.short_exp)
        mid_iv = (iv_for("short_put") + iv_for("short_call")) / 2  # same strike, avg IVs
        return (
            2 * _bs_price(current_price, pos.short_put, T, r, mid_iv, True)
            - _bs_price(current_price, pos.long_put, T, r, iv_for("long_put"), True)
            - _bs_price(current_price, pos.long_call, T, r, iv_for("long_call"), True)
        )
    else:
        # Iron Condor and Iron Butterfly: 4 legs with correct put/call types
        T = tte(pos.short_exp)
        return (
            _bs_price(current_price, pos.short_put, T, r, iv_for("short_put"), False)
            + _bs_price(current_price, pos.short_call, T, r, iv_for("short_call"), True)
            - _bs_price(current_price, pos.long_put, T, r, iv_for("long_put"), False)
            - _bs_price(current_price, pos.long_call, T, r, iv_for("long_call"), True)
        )


def _build_leg_list(pos, short_exp_str: str | None, long_exp_str: str | None) -> list[dict]:
    """Build leg descriptor list with correct option_types per strategy.

    For butterfly, all legs are the same type (calls).
    For iron_condor/iron_butterfly/DD/DC, puts are puts and calls are calls.
    """
    if pos.strategy == "butterfly":
        # Butterfly: long_put=lower, short_put=middle, short_call=middle, long_call=upper
        # All legs are the same option type (call by default)
        return [
            {"strike": pos.short_put, "exp": short_exp_str, "option_type": "call", "key": "short_put"},
            {"strike": pos.short_call, "exp": short_exp_str, "option_type": "call", "key": "short_call"},
            {"strike": pos.long_put, "exp": short_exp_str, "option_type": "call", "key": "long_put"},
            {"strike": pos.long_call, "exp": short_exp_str, "option_type": "call", "key": "long_call"},
        ]
    # Default: standard put/call mapping for IC, IB, DD, DC
    return [
        {"strike": pos.short_put, "exp": short_exp_str, "option_type": "put", "key": "short_put"},
        {"strike": pos.short_call, "exp": short_exp_str, "option_type": "call", "key": "short_call"},
        {"strike": pos.long_put, "exp": long_exp_str or short_exp_str, "option_type": "put", "key": "long_put"},
        {"strike": pos.long_call, "exp": long_exp_str or short_exp_str, "option_type": "call", "key": "long_call"},
    ]


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

    current_value = None
    unrealized_pnl = None
    pnl_pct = None
    pricing_source = None

    if current_price:
        # 1) Try live option quotes from Tradier chains (mid prices + IV)
        short_exp_str = str(pos.short_exp) if pos.short_exp else None
        long_exp_str = str(pos.long_exp) if pos.long_exp else None

        legs = _build_leg_list(pos, short_exp_str, long_exp_str)

        val = None
        leg_quotes = None
        if short_exp_str:
            try:
                leg_quotes = await _get_leg_quotes(request, pos.symbol, legs)
                val = _spread_val_from_quotes(leg_quotes)
                if val is not None:
                    pricing_source = "live_quotes"
            except Exception as e:
                logger.debug("Live quote repricing failed: %s", e)

        # 2) Fall back to BS with per-leg IV from Tradier (or 20% default)
        if val is None:
            leg_ivs = None
            if leg_quotes:
                leg_ivs = {k: v.get("iv") for k, v in leg_quotes.items()}
            val = _bs_spread_val(pos, current_price, leg_ivs)
            pricing_source = "black_scholes_live_iv" if leg_ivs and any(v is not None for v in leg_ivs.values()) else "black_scholes"

        current_value = round(val, 4)
        unrealized_pnl = _compute_unrealized_pnl(
            pos.entry_price, val, pos.contracts, pos.strategy,
            pos.max_profit, pos.max_loss,
        )

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
        "pricing_source": pricing_source,
        "entry_credit": pos.entry_credit,
        "entry_price": pos.entry_price,
        "max_profit": pos.max_profit,
        "max_loss": pos.max_loss,
        "is_credit": pos.strategy in CREDIT_STRATEGIES,
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
    marked = 0

    for pos in open_positions:
        try:
            # Try live option quotes first, fall back to BS
            short_exp_str = str(pos.short_exp) if pos.short_exp else None
            long_exp_str = str(pos.long_exp) if pos.long_exp else None
            legs = _build_leg_list(pos, short_exp_str, long_exp_str)

            val = None
            leg_quotes = None
            if short_exp_str:
                try:
                    leg_quotes = await _get_leg_quotes(request, pos.symbol, legs)
                    val = _spread_val_from_quotes(leg_quotes)
                except Exception:
                    pass

            if val is None:
                leg_ivs = {k: v.get("iv") for k, v in leg_quotes.items()} if leg_quotes else None
                val = _bs_spread_val(pos, current_price, leg_ivs)

            dte_val = (pos.short_exp - today_date).days if pos.short_exp else None
            unrealized = _compute_unrealized_pnl(
                pos.entry_price, val, pos.contracts, pos.strategy,
                pos.max_profit, pos.max_loss,
            )

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
            {"name": "Entry", "value": f"{'+'if pos.strategy in CREDIT_STRATEGIES else '-'}${pos.entry_credit:,.2f}", "inline": True},
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


# ---------------------------------------------------------------------------
# GEX Profile → Discord chart generators + endpoints
# ---------------------------------------------------------------------------


def _generate_net_gex_chart(strikes: list[dict], header: dict, levels: dict) -> bytes | None:
    """Generate a Net GEX horizontal bar chart as PNG bytes (mirrors frontend CSS bars)."""
    try:
        import io
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        if not strikes:
            return None

        price = header.get("price", 0)
        sorted_s = sorted(strikes, key=lambda s: abs(s["strike"] - price))[:40]
        sorted_s.sort(key=lambda s: s["strike"], reverse=True)

        strike_labels = [f"${s['strike']:.0f}" for s in sorted_s]
        net_gammas = [s["net_gamma"] for s in sorted_s]
        colors = ["#22c55e" if g >= 0 else "#ef4444" for g in net_gammas]

        fig, ax = plt.subplots(figsize=(8, max(len(sorted_s) * 0.22, 4)), dpi=150)
        fig.patch.set_facecolor("#0d0d18")
        ax.set_facecolor("#0d0d18")

        ax.barh(range(len(sorted_s)), net_gammas, color=colors, height=0.7, alpha=0.8)

        ax.set_yticks(range(len(sorted_s)))
        ax.set_yticklabels(strike_labels, fontsize=8, color="#9ca3af", fontfamily="monospace")

        # Mark key levels
        flip = levels.get("gex_flip")
        cw = levels.get("call_wall")
        pw = levels.get("put_wall")
        for i, s in enumerate(sorted_s):
            if price and abs(s["strike"] - price) <= 1:
                ax.barh(i, net_gammas[i], color="#f59e0b", height=0.7, alpha=0.9)
                ax.annotate("PRICE", xy=(0, i), fontsize=7, color="#f59e0b",
                            fontweight="bold", va="center", ha="left")
            elif flip and abs(s["strike"] - flip) <= 1:
                ax.annotate("FLIP", xy=(0, i), fontsize=7, color="#eab308",
                            fontweight="bold", va="center", ha="left")
            elif cw and abs(s["strike"] - cw) <= 1:
                ax.annotate("CALL WALL", xy=(0, i), fontsize=7, color="#06b6d4",
                            fontweight="bold", va="center", ha="left")
            elif pw and abs(s["strike"] - pw) <= 1:
                ax.annotate("PUT WALL", xy=(0, i), fontsize=7, color="#a855f7",
                            fontweight="bold", va="center", ha="left")

        ax.axvline(x=0, color="#475569", linewidth=0.7, linestyle="--")
        ax.set_xlabel("Net Gamma Exposure", color="#888", fontsize=9, fontfamily="monospace")
        ax.set_title(
            f"{header.get('symbol', 'SPY')} Net GEX by Strike · Spot ${price:,.2f}",
            color="#fff", fontsize=11, fontfamily="monospace", fontweight="bold", pad=10,
        )
        ax.tick_params(colors="#555", labelsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color("#1a1a2e")
        ax.spines["left"].set_color("#1a1a2e")
        ax.grid(axis="x", color="#1a1a2e", linewidth=0.5, alpha=0.5)
        ax.invert_yaxis()

        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor="#0d0d18", edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        logger.error(f"[Discord] Net GEX chart generation failed: {e}")
        return None


def _generate_callput_gex_chart(strikes: list[dict], header: dict, levels: dict) -> bytes | None:
    """Generate a bidirectional Call vs Put GEX bar chart as PNG bytes."""
    try:
        import io
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        if not strikes:
            return None

        price = header.get("price", 0)
        sorted_s = sorted(strikes, key=lambda s: abs(s["strike"] - price))[:40]
        sorted_s.sort(key=lambda s: s["strike"], reverse=True)

        strike_labels = [f"${s['strike']:.0f}" for s in sorted_s]
        call_gammas = [s.get("call_gamma", 0) for s in sorted_s]
        put_gammas = [-(s.get("put_gamma", 0)) for s in sorted_s]  # negative for visual

        y_pos = np.arange(len(sorted_s))

        fig, ax = plt.subplots(figsize=(8, max(len(sorted_s) * 0.22, 4)), dpi=150)
        fig.patch.set_facecolor("#0d0d18")
        ax.set_facecolor("#0d0d18")

        ax.barh(y_pos, call_gammas, height=0.4, color="#22c55e", alpha=0.75, label="Call Gamma")
        ax.barh(y_pos, put_gammas, height=0.4, color="#ef4444", alpha=0.75, label="Put Gamma")

        ax.set_yticks(y_pos)
        ax.set_yticklabels(strike_labels, fontsize=8, color="#9ca3af", fontfamily="monospace")

        # Reference lines for key levels
        flip = levels.get("gex_flip")
        cw = levels.get("call_wall")
        pw = levels.get("put_wall")
        for i, s in enumerate(sorted_s):
            if price and abs(s["strike"] - price) <= 1:
                ax.axhline(y=i, color="#448aff", linewidth=1.5, alpha=0.6)
            if flip and abs(s["strike"] - flip) <= 1:
                ax.axhline(y=i, color="#eab308", linewidth=1.2, linestyle="--", alpha=0.6)
            if cw and abs(s["strike"] - cw) <= 1:
                ax.axhline(y=i, color="#06b6d4", linewidth=1.2, linestyle=":", alpha=0.6)
            if pw and abs(s["strike"] - pw) <= 1:
                ax.axhline(y=i, color="#a855f7", linewidth=1.2, linestyle=":", alpha=0.6)

        ax.axvline(x=0, color="#475569", linewidth=0.7, linestyle="--")
        ax.set_xlabel("Gamma Exposure", color="#888", fontsize=9, fontfamily="monospace")
        ax.set_title(
            f"{header.get('symbol', 'SPY')} Call vs Put GEX · Spot ${price:,.2f}",
            color="#fff", fontsize=11, fontfamily="monospace", fontweight="bold", pad=10,
        )
        ax.tick_params(colors="#555", labelsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color("#1a1a2e")
        ax.spines["left"].set_color("#1a1a2e")
        ax.grid(axis="x", color="#1a1a2e", linewidth=0.5, alpha=0.5)
        ax.legend(loc="lower right", fontsize=8, facecolor="#0d0d18", edgecolor="#1a1a2e",
                  labelcolor="#9ca3af")
        ax.invert_yaxis()

        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor="#0d0d18", edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        logger.error(f"[Discord] Call vs Put chart generation failed: {e}")
        return None


def _generate_intraday_gex_chart(bars: list[dict], ticks: list[dict],
                                  header: dict, levels: dict) -> bytes | None:
    """Generate an intraday candlestick + GEX overlay chart as PNG bytes."""
    try:
        import io
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from datetime import datetime, timezone, timedelta

        if not bars and not ticks:
            return None

        ct_offset = timedelta(hours=-6)  # CDT (CT during DST)

        fig, ax1 = plt.subplots(figsize=(10, 4.5), dpi=150)
        fig.patch.set_facecolor("#0d0d18")
        ax1.set_facecolor("#0d0d18")

        if bars:
            times = []
            for b in bars:
                t = b.get("time", "")
                try:
                    dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
                    times.append(dt + ct_offset)
                except Exception:
                    times.append(datetime.now())

            opens = [b["open"] for b in bars]
            highs = [b["high"] for b in bars]
            lows = [b["low"] for b in bars]
            closes = [b["close"] for b in bars]

            bar_width = 0.002  # fraction of day
            for i in range(len(bars)):
                color = "#22c55e" if closes[i] >= opens[i] else "#ef4444"
                ax1.plot([times[i], times[i]], [lows[i], highs[i]],
                         color=color, linewidth=0.8)
                ax1.bar(times[i], closes[i] - opens[i], bottom=min(opens[i], closes[i]),
                        width=bar_width, color=color, alpha=0.8, edgecolor=color)
        elif ticks:
            times = []
            prices = []
            for t in ticks:
                if t.get("spot_price") is None:
                    continue
                try:
                    dt = datetime.fromisoformat(t["time"].replace("Z", "+00:00"))
                    times.append(dt + ct_offset)
                    prices.append(t["spot_price"])
                except Exception:
                    pass
            if times:
                ax1.plot(times, prices, color="#3b82f6", linewidth=1.5)

        # Reference lines
        flip = levels.get("gex_flip")
        cw = levels.get("call_wall")
        pw = levels.get("put_wall")
        if flip:
            ax1.axhline(y=flip, color="#eab308", linewidth=1.5, linestyle="--", alpha=0.7)
            ax1.text(0.01, flip, f" FLIP ${flip:.0f}", transform=ax1.get_yaxis_transform(),
                     color="#eab308", fontsize=8, fontfamily="monospace", va="bottom")
        if cw:
            ax1.axhline(y=cw, color="#06b6d4", linewidth=1.5, linestyle=":", alpha=0.7)
            ax1.text(0.01, cw, f" CALL WALL ${cw:.0f}", transform=ax1.get_yaxis_transform(),
                     color="#06b6d4", fontsize=8, fontfamily="monospace", va="bottom")
        if pw:
            ax1.axhline(y=pw, color="#a855f7", linewidth=1.5, linestyle=":", alpha=0.7)
            ax1.text(0.01, pw, f" PUT WALL ${pw:.0f}", transform=ax1.get_yaxis_transform(),
                     color="#a855f7", fontsize=8, fontfamily="monospace", va="top")

        # GEX overlay on secondary y-axis
        if ticks:
            gex_times = []
            gex_vals = []
            for t in ticks:
                ng = t.get("net_gamma")
                if ng is None:
                    continue
                try:
                    dt = datetime.fromisoformat(t["time"].replace("Z", "+00:00"))
                    gex_times.append(dt + ct_offset)
                    gex_vals.append(ng)
                except Exception:
                    pass
            if gex_times:
                ax2 = ax1.twinx()
                ax2.fill_between(gex_times, gex_vals, alpha=0.15, color="#3b82f6")
                ax2.plot(gex_times, gex_vals, color="#3b82f6", linewidth=0.8, alpha=0.5)
                ax2.set_ylabel("Net GEX", color="#3b82f6", fontsize=9, fontfamily="monospace")
                ax2.tick_params(colors="#3b82f6", labelsize=7)
                ax2.spines["right"].set_color("#1a1a2e")
                ax2.spines["top"].set_visible(False)

        price = header.get("price", 0)
        symbol = header.get("symbol", "SPY")
        ax1.set_title(
            f"{symbol} Intraday 5m · Spot ${price:,.2f}",
            color="#fff", fontsize=11, fontfamily="monospace", fontweight="bold", pad=10,
        )
        ax1.set_ylabel("Price", color="#888", fontsize=9, fontfamily="monospace")
        ax1.tick_params(colors="#555", labelsize=8)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%I:%M %p"))
        ax1.spines["top"].set_visible(False)
        ax1.spines["right"].set_color("#1a1a2e")
        ax1.spines["bottom"].set_color("#1a1a2e")
        ax1.spines["left"].set_color("#1a1a2e")
        ax1.grid(axis="both", color="#1a1a2e", linewidth=0.5, alpha=0.5)

        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor="#0d0d18", edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        logger.error(f"[Discord] Intraday chart generation failed: {e}")
        return None


def _format_gex(num: float) -> str:
    """Format GEX value with B/M/K suffix."""
    abs_val = abs(num)
    if abs_val >= 1e9:
        return f"{num / 1e9:.2f}B"
    if abs_val >= 1e6:
        return f"{num / 1e6:.2f}M"
    if abs_val >= 1e3:
        return f"{num / 1e3:.2f}K"
    return f"{num:.2f}"


async def _fetch_gex_data(request: Request, symbol: str) -> dict:
    """Fetch GEX analysis data from AlphaGEX backend."""
    http = request.app.state.http
    resp = await http.get(
        f"{ALPHAGEX_BASE_URL}/api/watchtower/gex-analysis",
        params={"symbol": symbol},
        timeout=20.0,
    )
    result = resp.json()
    if not result.get("success"):
        raise HTTPException(502, "GEX data unavailable")
    return result["data"]


async def _fetch_intraday_data(request: Request, symbol: str) -> tuple[list, list]:
    """Fetch intraday ticks and bars from AlphaGEX backend."""
    http = request.app.state.http
    ticks_resp, bars_resp = await asyncio.gather(
        http.get(
            f"{ALPHAGEX_BASE_URL}/api/watchtower/intraday-ticks",
            params={"symbol": symbol, "interval": 5, "fallback": "true"},
            timeout=20.0,
        ),
        http.get(
            f"{ALPHAGEX_BASE_URL}/api/watchtower/intraday-bars",
            params={"symbol": symbol, "interval": "5min", "fallback": "true"},
            timeout=20.0,
        ),
    )
    ticks_json = ticks_resp.json()
    bars_json = bars_resp.json()
    ticks = ticks_json.get("data", {}).get("ticks", []) if ticks_json.get("success") else []
    bars = bars_json.get("data", {}).get("bars", []) if bars_json.get("success") else []
    return ticks, bars


def _gex_header_embed_fields(header: dict, levels: dict) -> list[dict]:
    """Build Discord embed fields from GEX header/levels data."""
    price = header.get("price", 0)
    net_gex = header.get("net_gex", 0)
    gamma_form = header.get("gamma_form", "—")
    rating = header.get("rating", "—")
    flip = levels.get("gex_flip")
    cw = levels.get("call_wall")
    pw = levels.get("put_wall")

    fields = [
        {"name": "Price", "value": f"${price:,.2f}", "inline": True},
        {"name": "Net GEX", "value": _format_gex(net_gex), "inline": True},
        {"name": "Gamma Regime", "value": gamma_form, "inline": True},
        {"name": "Rating", "value": rating, "inline": True},
    ]
    if flip:
        dist = ((price - flip) / price * 100) if price else 0
        fields.append({"name": "Flip Point", "value": f"${flip:,.2f} ({dist:+.1f}%)", "inline": True})
    if cw:
        dist = ((cw - price) / price * 100) if price else 0
        fields.append({"name": "Call Wall", "value": f"${cw:,.2f} (+{dist:.1f}%)", "inline": True})
    if pw:
        dist = ((price - pw) / price * 100) if price else 0
        fields.append({"name": "Put Wall", "value": f"${pw:,.2f} (-{dist:.1f}%)", "inline": True})
    return fields


@router.post("/discord/push-gex-net")
async def discord_push_gex_net(request: Request, symbol: str = "SPY"):
    """Push Net GEX bar chart to Discord."""
    if not _discord_url():
        raise HTTPException(503, "DISCORD_WEBHOOK_URL not configured")

    gex_data = await _fetch_gex_data(request, symbol)
    header = gex_data.get("header", {})
    header["symbol"] = symbol
    levels = gex_data.get("levels", {})
    strikes = gex_data.get("gex_chart", {}).get("strikes", [])

    chart_bytes = _generate_net_gex_chart(strikes, header, levels)

    net_gex = header.get("net_gex", 0)
    color = 0x22C55E if net_gex >= 0 else 0xFF1744
    embed = {
        "title": f"\U0001f4ca {symbol} Net GEX by Strike · ${header.get('price', 0):,.2f}",
        "color": color,
        "fields": _gex_header_embed_fields(header, levels),
        "footer": {"text": f"SpreadWorks · GEX Profile · {gex_data.get('expiration', '')}"},
        "timestamp": _now_ct().isoformat(),
    }

    ok = _send_discord_embed(embed, image_bytes=chart_bytes)
    if not ok:
        raise HTTPException(502, "Failed to post to Discord")
    return {"posted": True}


@router.post("/discord/push-gex-callput")
async def discord_push_gex_callput(request: Request, symbol: str = "SPY"):
    """Push Call vs Put GEX chart to Discord."""
    if not _discord_url():
        raise HTTPException(503, "DISCORD_WEBHOOK_URL not configured")

    gex_data = await _fetch_gex_data(request, symbol)
    header = gex_data.get("header", {})
    header["symbol"] = symbol
    levels = gex_data.get("levels", {})
    strikes = gex_data.get("gex_chart", {}).get("strikes", [])

    chart_bytes = _generate_callput_gex_chart(strikes, header, levels)

    net_gex = header.get("net_gex", 0)
    color = 0x22C55E if net_gex >= 0 else 0xFF1744
    embed = {
        "title": f"\U0001f4ca {symbol} Call vs Put GEX · ${header.get('price', 0):,.2f}",
        "color": color,
        "fields": _gex_header_embed_fields(header, levels),
        "footer": {"text": f"SpreadWorks · GEX Profile · {gex_data.get('expiration', '')}"},
        "timestamp": _now_ct().isoformat(),
    }

    ok = _send_discord_embed(embed, image_bytes=chart_bytes)
    if not ok:
        raise HTTPException(502, "Failed to post to Discord")
    return {"posted": True}


@router.post("/discord/push-gex-intraday")
async def discord_push_gex_intraday(request: Request, symbol: str = "SPY"):
    """Push Intraday 5m candlestick + GEX overlay chart to Discord."""
    if not _discord_url():
        raise HTTPException(503, "DISCORD_WEBHOOK_URL not configured")

    gex_data = await _fetch_gex_data(request, symbol)
    header = gex_data.get("header", {})
    header["symbol"] = symbol
    levels = gex_data.get("levels", {})

    ticks, bars = await _fetch_intraday_data(request, symbol)

    chart_bytes = _generate_intraday_gex_chart(bars, ticks, header, levels)

    net_gex = header.get("net_gex", 0)
    color = 0x22C55E if net_gex >= 0 else 0xFF1744

    fields = _gex_header_embed_fields(header, levels)
    fields.append({"name": "Candles", "value": f"{len(bars)} bars", "inline": True})

    embed = {
        "title": f"\U0001f4ca {symbol} Intraday 5m · ${header.get('price', 0):,.2f}",
        "color": color,
        "fields": fields,
        "footer": {"text": "SpreadWorks · GEX Profile · Intraday"},
        "timestamp": _now_ct().isoformat(),
    }

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
    net_premium = sum(
        p.entry_credit if p.strategy in CREDIT_STRATEGIES else -p.entry_credit
        for p in open_positions
    )

    lines = []
    for pos in open_positions:
        strat_label = STRATEGY_LABELS.get(pos.strategy, pos.strategy)
        dte = (pos.short_exp - _today_ct()).days if pos.short_exp else "?"
        entry_sign = "+" if pos.strategy in CREDIT_STRATEGIES else "-"
        lines.append(
            f"{pos.symbol} {strat_label} \u00b7 {_strikes_str(pos)} \u00b7 "
            f"Entry: {entry_sign}${pos.entry_credit:,.2f}\n"
            f"Max Profit: ${pos.max_profit:,.2f} | Max Loss: ${pos.max_loss:,.2f} | {dte}DTE"
            if pos.max_profit is not None and pos.max_loss is not None
            else f"{pos.symbol} {strat_label} \u00b7 {_strikes_str(pos)} \u00b7 "
                 f"Entry: {entry_sign}${pos.entry_credit:,.2f} | {dte}DTE"
        )

    positions_text = "\n\n".join(lines)

    premium_sign = "+" if net_premium >= 0 else "-"
    embed = {
        "title": f"\U0001f4cb TODAY'S OPEN SPREADS \u00b7 {today_str}",
        "color": 0x448AFF,
        "description": positions_text,
        "fields": [
            {"name": "Net Premium", "value": f"{premium_sign}${abs(net_premium):,.2f}", "inline": True},
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
            "is_credit": pos.strategy in CREDIT_STRATEGIES,
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

    net_premium = sum(
        p.entry_credit if p.strategy in CREDIT_STRATEGIES else -p.entry_credit
        for p in open_positions
    )
    pnl_pct = round(total_unrealized / abs(net_premium) * 100, 1) if net_premium else 0

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
                    f"entry {'+'if p.get('is_credit') else '-'}${p['entry_credit']:,.2f}, unrealized ${p['unrealized_pnl']:+,.2f}, "
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
                "value": f"{'+'if total_unrealized >= 0 else ''}${total_unrealized:,.2f} ({pnl_pct:+.1f}% of net premium)",
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
                # Try live option quotes first
                short_exp_str = str(pos.short_exp) if pos.short_exp else None
                long_exp_str = str(pos.long_exp) if pos.long_exp else None
                legs = _build_leg_list(pos, short_exp_str, long_exp_str)

                val = None
                leg_quotes = None
                if short_exp_str:
                    try:
                        leg_quotes = await _get_leg_quotes(request, pos.symbol, legs)
                        val = _spread_val_from_quotes(leg_quotes)
                    except Exception:
                        pass

                if val is None:
                    leg_ivs = {k: v.get("iv") for k, v in leg_quotes.items()} if leg_quotes else None
                    val = _bs_spread_val(pos, spot, leg_ivs)

                current_value = round(val, 4)
                unrealized_pnl = _compute_unrealized_pnl(
                    pos.entry_price, val, pos.contracts, pos.strategy,
                    pos.max_profit, pos.max_loss,
                )

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

    entry_sign = "+" if pos.strategy in CREDIT_STRATEGIES else "-"
    fields.append({
        "name": "Entry Credit" if pos.strategy in CREDIT_STRATEGIES else "Entry Debit",
        "value": f"{entry_sign}${pos.entry_credit:,.2f}",
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
    n = pos.contracts
    sigma = 0.20
    r = RISK_FREE_RATE

    # Convert entry_price (always positive) back to entry_cost convention:
    # Credit strategies: entry_cost = -entry_price (negative = credit received)
    # Debit strategies: entry_cost = +entry_price (positive = debit paid)
    if pos.strategy in CREDIT_STRATEGIES:
        entry_cost = -pos.entry_price
    else:
        entry_cost = pos.entry_price

    # Get spot price for the marker
    spot = None
    try:
        q = await _get_quote(request, pos.symbol)
        spot = q.get("last")
    except Exception:
        pass

    # Route to _scan_pnl_profile for strategies with time value or known payoff
    if pos.strategy == "double_diagonal" and pos.long_exp:
        profile = _scan_pnl_profile(
            "double_diagonal", spot or ((sp + sc) / 2),
            {"lp": lp, "sp": sp, "sc": sc, "lc": lc},
            {"short": str(pos.short_exp), "long": str(pos.long_exp)},
            r, sigma, entry_cost, n,
        )
    elif pos.strategy == "double_calendar" and pos.long_exp:
        profile = _scan_pnl_profile(
            "double_calendar", spot or ((sp + sc) / 2),
            {"ps": sp, "cs": sc},
            {"front": str(pos.short_exp), "back": str(pos.long_exp)},
            r, sigma, entry_cost, n,
        )
    elif pos.strategy == "butterfly":
        profile = _scan_pnl_profile(
            "butterfly", spot or sp,
            {"lower": lp, "middle": sp, "upper": lc, "is_call": True},
            {"exp": str(pos.short_exp)},
            r, sigma, entry_cost, n,
        )
    elif pos.strategy == "iron_butterfly":
        profile = _scan_pnl_profile(
            "iron_butterfly", spot or sp,
            {"lp": lp, "short": sp, "lc": lc},
            {"exp": str(pos.short_exp)},
            r, sigma, entry_cost, n,
        )
    else:
        # Iron Condor
        profile = _scan_pnl_profile(
            "iron_condor", spot or ((sp + sc) / 2),
            {"lp": lp, "sp": sp, "sc": sc, "lc": lc},
            {"exp": str(pos.short_exp)},
            r, sigma, entry_cost, n,
        )

    # Use stored max_profit/max_loss from position creation for consistency
    # with the card display. The curve shape is recalculated dynamically
    # (correct for time-dependent strategies like DD/DC), but the boundary
    # labels should match the card values.
    max_profit = pos.max_profit if pos.max_profit is not None else profile["max_profit"]
    max_loss = pos.max_loss if pos.max_loss is not None else profile["max_loss"]

    return {
        "position_id": position_id,
        "spot_price": spot,
        "pnl_curve": profile["pnl_curve"],
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakevens": {
            "lower": profile["lower_breakeven"],
            "upper": profile["upper_breakeven"],
        },
    }


# ---------------------------------------------------------------------------
# GEX Profile — proxy endpoints to main AlphaGEX watchtower API
# ---------------------------------------------------------------------------


@router.get("/gex-analysis")
async def proxy_gex_analysis(request: Request, symbol: str = "SPY"):
    """Proxy to AlphaGEX /api/watchtower/gex-analysis."""
    http = request.app.state.http
    try:
        resp = await http.get(
            f"{ALPHAGEX_BASE_URL}/api/watchtower/gex-analysis",
            params={"symbol": symbol},
            timeout=20.0,
        )
        return resp.json()
    except Exception as e:
        raise HTTPException(502, f"AlphaGEX proxy error: {e}")


@router.get("/intraday-ticks")
async def proxy_intraday_ticks(
    request: Request,
    symbol: str = "SPY",
    interval: int = 5,
    fallback: bool = False,
):
    """Proxy to AlphaGEX /api/watchtower/intraday-ticks."""
    http = request.app.state.http
    params: dict[str, Any] = {"symbol": symbol, "interval": interval}
    if fallback:
        params["fallback"] = "true"
    try:
        resp = await http.get(
            f"{ALPHAGEX_BASE_URL}/api/watchtower/intraday-ticks",
            params=params,
            timeout=20.0,
        )
        return resp.json()
    except Exception as e:
        raise HTTPException(502, f"AlphaGEX proxy error: {e}")


@router.get("/intraday-bars")
async def proxy_intraday_bars(
    request: Request,
    symbol: str = "SPY",
    interval: str = "5min",
    fallback: bool = False,
):
    """Proxy to AlphaGEX /api/watchtower/intraday-bars."""
    http = request.app.state.http
    params: dict[str, Any] = {"symbol": symbol, "interval": interval}
    if fallback:
        params["fallback"] = "true"
    try:
        resp = await http.get(
            f"{ALPHAGEX_BASE_URL}/api/watchtower/intraday-bars",
            params=params,
            timeout=20.0,
        )
        return resp.json()
    except Exception as e:
        raise HTTPException(502, f"AlphaGEX proxy error: {e}")
